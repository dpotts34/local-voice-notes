from __future__ import annotations

import asyncio
import fcntl
import hashlib
import os
import stat
import tempfile
import uuid
from pathlib import Path

from .clients import ExternalClients
from .config import Config
from .mounts import archive_available
from .spool import _fsync_directory, durable_unlink, open_private_directory
from .store import Job, JobStore, LeaseLost
from .writer import InboxWriter


class PostWriteSyncError(RuntimeError):
    pass


async def _settled_to_thread(function, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass
            except BaseException:
                break
        try:
            task.result()
        except BaseException:
            pass
        raise cancellation


class Worker:
    def __init__(
        self, config: Config, store: JobStore, clients: ExternalClients, writer: InboxWriter,
        syncer=None,
    ):
        self.config = config
        self.store = store
        self.clients = clients
        self.writer = writer
        self.syncer = syncer
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self.owner = str(uuid.uuid4())
        self.lease_seconds = 300

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                try:
                    await _settled_to_thread(
                        self.store.enforce_archive_retention,
                        self.config.archive_max_bytes,
                        self.config.archive_dir,
                    )
                except Exception:
                    pass
                pending = self.store.recoverable(self.config.max_retries)
                delay = self.retry_delay(pending[0].retry_count) if pending else 0
                if delay:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=delay)
                        break
                    except TimeoutError:
                        pass
                self._wake.clear()
                processed = await self.run_once()
                if processed:
                    continue
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5)
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                self._wake.clear()
                if self._stop.is_set():
                    break
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5)
                except TimeoutError:
                    pass

    async def run_once(self) -> bool:
        try:
            lock_fd = self._acquire_worker_lock()
        except Exception:
            return False
        try:
            if lock_fd is None:
                return False
            try:
                # The exclusive worker lock proves any other owner's claim is orphaned.
                for pending in self.store.recoverable(self.config.max_retries):
                    if pending.claim_owner and pending.claim_owner != self.owner:
                        self.store.release_claim(pending.request_id, pending.claim_owner)
                job = await _settled_to_thread(
                    self.store.claim_next, self.owner, self.lease_seconds, self.config.max_retries
                )
            except Exception:
                return False
            if job is None:
                return False
            if job.status == "failed":
                delivered = False
                try:
                    nonce = self.store.ensure_notification_nonce(job.request_id, self.owner)
                    event_id = await self.clients.notify(
                        "failed", job.note_path, job.request_id, job.thread_id, nonce,
                    )
                    if not event_id:
                        raise ValueError("ntfy returned no valid event ID")
                    self.store.transition(
                        job.request_id, "failed", owner=self.owner, notification_event_id=event_id,
                    )
                    delivered = True
                except LeaseLost:
                    pass
                except Exception:
                    pass
                finally:
                    try:
                        self.store.release_claim(job.request_id, self.owner)
                    except Exception:
                        pass
                return delivered
            try:
                await self._process(job)
            except LeaseLost:
                pass
            except Exception as error:
                current = self.store.get(job.request_id) or job
                stage = "lint_or_sync" if isinstance(error, PostWriteSyncError) else self._stage(current.status)
                notification_nonce = None
                if current.retry_count + 1 >= self.config.max_retries:
                    notification_nonce = self.store.ensure_notification_nonce(job.request_id, self.owner)
                failed = self.store.record_failure(
                    job.request_id, stage, f"{type(error).__name__}: {error}", owner=self.owner,
                    max_retries=self.config.max_retries,
                )
                if failed.status == "failed":
                    event_id = None
                    try:
                        event_id = await self.clients.notify(
                            "failed", failed.note_path, failed.request_id, failed.thread_id,
                            notification_nonce or failed.notification_nonce,
                        )
                    except Exception:
                        pass
                    if event_id:
                        self.store.transition(job.request_id, "failed", notification_event_id=event_id)
            finally:
                try:
                    self.store.release_claim(job.request_id, self.owner)
                except Exception:
                    pass
            return True
        finally:
            if lock_fd is not None:
                os.close(lock_fd)

    def _acquire_worker_lock(self) -> int | None:
        path = self.store.path.with_name(self.store.path.name + ".worker.lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            # ponytail: global worker lock caps throughput at one job; use per-job locks only if parallel workers are required.
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            os.close(fd)
            return None
        except BaseException:
            os.close(fd)
            raise

    async def _process(self, original: Job) -> None:
        job = self.store.get(original.request_id) or original
        if job.status == "received":
            with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                archive = await _settled_to_thread(self._archive, job)
            job = self.store.transition(
                job.request_id, "archived", owner=self.owner,
                archive_path=str(archive), error_stage=None, error_message=None
            )
        if job.status == "archived":
            archive = Path(job.archive_path or "")
            with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                transcript = await self.clients.transcribe(
                    archive, job.content_type, job.sha256, job.byte_count
                )
            with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                transcript_path = await _settled_to_thread(self._save_transcript, job.request_id, transcript)
            job = self.store.transition(
                job.request_id, "transcribed", owner=self.owner,
                transcript_path=str(transcript_path), error_stage=None, error_message=None
            )
        if job.status == "transcribed":
            job = self.store.transition(
                job.request_id, "formatting", owner=self.owner, error_stage=None, error_message=None
            )
        action = None
        needs_format = job.status == "formatting" or (
            job.status == "writing" and (
                job.note_path is None or job.notification_summary is None or job.note_sha256 is None
            )
        )
        if needs_format:
            if not job.transcript_path:
                raise OSError("transcript path is missing")
            transcript = await _settled_to_thread(Path(job.transcript_path).read_text, encoding="utf-8")
            with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                action = await self.clients.format_note(transcript)
        if job.status == "formatting":
            job = self.store.transition(
                job.request_id, "writing", owner=self.owner, error_stage=None, error_message=None
            )
        if job.status == "writing":
            if (
                job.note_path is not None
                and job.notification_summary is not None
                and job.note_sha256 is not None
            ):
                with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                    relative = await _settled_to_thread(self.writer.verify_existing, job)
                    await _settled_to_thread(self.writer.ensure_thread_index, job)
                summary = job.notification_summary
            else:
                if action is None:
                    raise RuntimeError("formatted note is missing")
                with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                    relative, note_sha256 = await _settled_to_thread(self.writer.write_verified, job, action)
                summary = action.summary
                job = self.store.transition(
                    job.request_id, "writing", owner=self.owner,
                    note_path=relative.as_posix(), notification_summary=summary, note_sha256=note_sha256,
                )
            if self.syncer is not None:
                try:
                    with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                        await _settled_to_thread(self.syncer.run, f"Add voice note {job.request_id}")
                except Exception as error:
                    raise PostWriteSyncError(str(error)) from error
            if not job.notification_event_id:
                with self.store.claimed_effect(job.request_id, self.owner, self.lease_seconds):
                    notification_nonce = self.store.ensure_notification_nonce(job.request_id, self.owner)
                    event_id = await self.clients.notify(
                        "completed", relative.as_posix(), job.request_id, job.thread_id,
                        notification_nonce, summary,
                    )
                    if not event_id:
                        raise ValueError("ntfy returned no valid event ID")
                    await _settled_to_thread(self.writer.verify_existing, job)
                job = self.store.transition(
                    job.request_id, "writing", owner=self.owner, notification_event_id=event_id
                )
            self.store.transition(
                job.request_id, "completed", owner=self.owner,
                note_path=relative.as_posix(), error_stage=None, error_message=None
            )
            try:
                await _settled_to_thread(
                    self.store.enforce_archive_retention,
                    self.config.archive_max_bytes,
                    self.config.archive_dir,
                )
            except Exception:
                pass

    def _archive(self, job: Job) -> Path:
        archive_fd = os.open(self.config.archive_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            available, details = archive_available(self.config.archive_dir, self.config.require_nfs_mount)
            if not available:
                if self.config.require_nfs_mount and not details["nfs_mount"]:
                    raise OSError("archive root is not the required NFS mount")
                raise OSError("archive root is unavailable")
            self._require_same_directory(self.config.archive_dir, archive_fd)
            source = Path(job.spool_path)
            destination = self.config.archive_dir / job.stored_filename
            try:
                self._verify(archive_fd, job.stored_filename, job)
            except FileNotFoundError:
                pass
            else:
                os.fsync(archive_fd)
                self._require_same_directory(self.config.archive_dir, archive_fd)
                return destination

            if source.parent != self.config.state_dir / "spool" or source.name != job.stored_filename:
                raise OSError("authoritative spool path conflict")
            source_directory_fd = open_private_directory(source.parent, label="spool")
            try:
                source_fd = os.open(
                    source.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                    dir_fd=source_directory_fd,
                )
            except BaseException:
                os.close(source_directory_fd)
                raise
            try:
                source_stat = os.fstat(source_fd)
            except BaseException:
                os.close(source_fd)
                os.close(source_directory_fd)
                raise
            if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size != job.byte_count:
                os.close(source_fd)
                os.close(source_directory_fd)
                raise OSError("authoritative spool is not the expected regular file")
            temp_name = f".archive-{uuid.uuid4().hex}"
            fd = -1
            try:
                fd = os.open(
                    temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600,
                    dir_fd=archive_fd,
                )
                outgoing = os.fdopen(fd, "wb")
                fd = -1
                digest = hashlib.sha256()
                size = 0
                with os.fdopen(source_fd, "rb") as incoming, outgoing:
                    source_fd = -1
                    while chunk := incoming.read(1024 * 1024):
                        size += len(chunk)
                        digest.update(chunk)
                        outgoing.write(chunk)
                    if size != job.byte_count or digest.hexdigest() != job.sha256:
                        raise OSError("authoritative spool integrity conflict")
                    current_source_dir = os.stat(source.parent, follow_symlinks=False)
                    held_source_dir = os.fstat(source_directory_fd)
                    if (
                        not stat.S_ISDIR(current_source_dir.st_mode)
                        or (current_source_dir.st_dev, current_source_dir.st_ino)
                        != (held_source_dir.st_dev, held_source_dir.st_ino)
                    ):
                        raise OSError("spool directory changed during archive")
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                try:
                    os.link(temp_name, job.stored_filename, src_dir_fd=archive_fd, dst_dir_fd=archive_fd)
                except FileExistsError:
                    self._verify(archive_fd, job.stored_filename, job)
                self._unlink_archive_temp(archive_fd, temp_name)
                self._verify(archive_fd, job.stored_filename, job)
                os.fsync(archive_fd)
                self._require_same_directory(self.config.archive_dir, archive_fd)
                return destination
            finally:
                if source_fd >= 0:
                    os.close(source_fd)
                os.close(source_directory_fd)
                if fd >= 0:
                    os.close(fd)
                self._unlink_archive_temp(archive_fd, temp_name)
        finally:
            os.close(archive_fd)

    @staticmethod
    def _verify(directory_fd: int, name: str, job: Job) -> None:
        digest = hashlib.sha256()
        size = 0
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            raise
        except OSError as error:
            raise OSError("archive destination is not a regular file") from error
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("archive destination is not a regular file")
            with os.fdopen(fd, "rb") as stream:
                fd = -1
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
        finally:
            if fd >= 0:
                os.close(fd)
        if size != job.byte_count or digest.hexdigest() != job.sha256:
            raise OSError("archive verification failed")

    @staticmethod
    def _unlink_archive_temp(directory_fd: int, name: str) -> None:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            return
        os.fsync(directory_fd)

    @staticmethod
    def _require_same_directory(path: Path, directory_fd: int) -> None:
        current = os.stat(path, follow_symlinks=False)
        held = os.fstat(directory_fd)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise OSError("archive directory changed during write")

    def _save_transcript(self, request_id: str, transcript: str) -> Path:
        directory = self.config.state_dir / "transcripts"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        final = directory / f"{request_id}.txt"
        fd, name = tempfile.mkstemp(prefix=".transcript-", dir=directory)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                stream.write(transcript)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, final)
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return final
        finally:
            durable_unlink(temporary)

    @staticmethod
    def retry_delay(retry_count: int) -> int:
        return 0 if retry_count <= 0 else min(2**retry_count, 60)

    @staticmethod
    def _stage(status: str) -> str:
        return {
            "received": "archive",
            "archived": "transcribe",
            "transcribed": "format",
            "formatting": "format",
            "writing": "write_or_notify",
        }.get(status, status)

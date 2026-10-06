from __future__ import annotations

import json
import fcntl
import hashlib
import os
import re
import stat
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Iterator

from .config import Config
from .note_action import NoteAction
from .store import Job


class UnsafeWrite(ValueError):
    pass


def slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFC", title)
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "-", normalized)
    slug = " ".join(slug.split()).strip(" .-")
    # Leave room for collision suffixes on filesystems with a 255-byte name limit.
    slug = slug.encode("utf-8")[:200].decode("utf-8", "ignore").rstrip(" .") or "Voice Note"
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", slug):
        slug = "_" + slug
    return slug


class InboxWriter:
    def __init__(self, config: Config):
        self.config = config

    def _inbox(self, *, open_fd: bool = False):
        inbox = self.config.inbox
        if inbox != Path("Voice Inbox") or inbox.is_absolute() or ".." in inbox.parts or not inbox.parts:
            raise UnsafeWrite("inbox must be vault-relative")
        vault = self.config.vault_dir
        if vault.resolve() != vault.absolute():
            raise UnsafeWrite("vault root must be canonical and not a symlink")
        if not vault.is_dir():
            raise OSError("vault root is unavailable")
        root = vault.resolve()
        target = root / inbox
        if target.is_symlink():
            raise UnsafeWrite("inbox must be a real directory, not a symlink")
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir() or target.resolve() != target.absolute():
            raise UnsafeWrite("inbox must be the canonical directory under the vault")
        if not open_fd:
            return target
        directory_fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if not self._same_directory(target, directory_fd):
                raise OSError("inbox directory changed during validation")
            return target, directory_fd
        except BaseException:
            os.close(directory_fd)
            raise

    def write(self, job: Job, action: NoteAction, *, now: datetime | None = None) -> Path:
        return self.write_verified(job, action, now=now)[0]

    def write_verified(
        self, job: Job, action: NoteAction, *, now: datetime | None = None
    ) -> tuple[Path, str]:
        self._validate_thread_id(job.thread_id)
        inbox, inbox_fd = self._inbox(open_fd=True)
        try:
            lock_fd = os.open(
                ".write.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=inbox_fd
            )
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                result = self._write(inbox, inbox_fd, job, action, now)
                self._update_thread_index(job.thread_id, inbox_fd)
                return result
            finally:
                os.close(lock_fd)
        finally:
            os.close(inbox_fd)

    def verify_existing(self, job: Job) -> Path:
        if job.note_path is None or job.note_sha256 is None:
            raise OSError("persisted note recovery metadata is missing")
        relative = Path(job.note_path)
        if (
            relative.is_absolute() or relative.as_posix() != job.note_path
            or relative.parent != self.config.inbox or relative.suffix != ".md"
        ):
            raise UnsafeWrite("persisted note path is outside the inbox")
        inbox, inbox_fd = self._inbox(open_fd=True)
        try:
            with self._read_regular(inbox_fd, relative.name) as content:
                identity = f'---\nrequest_id: "{job.request_id}"\n'.encode()
                if not content.startswith(identity):
                    raise OSError("persisted note request identity conflict")
                if hashlib.sha256(content).hexdigest() != job.note_sha256:
                    raise OSError("persisted note integrity conflict")
            if not self._same_directory(inbox, inbox_fd):
                raise OSError("inbox directory changed during validation")
            return relative
        finally:
            os.close(inbox_fd)

    def ensure_thread_index(self, job: Job) -> None:
        self._validate_thread_id(job.thread_id)
        _, inbox_fd = self._inbox(open_fd=True)
        try:
            lock_fd = os.open(
                ".write.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=inbox_fd
            )
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                self._update_thread_index(job.thread_id, inbox_fd)
            finally:
                os.close(lock_fd)
        finally:
            os.close(inbox_fd)

    @staticmethod
    def _validate_thread_id(thread_id: str) -> None:
        try:
            if str(uuid.UUID(thread_id)) != thread_id:
                raise ValueError
        except (ValueError, AttributeError, TypeError) as error:
            raise UnsafeWrite("thread_id must be a canonical UUID") from error

    @contextmanager
    def _read_regular(self, directory_fd: int, name: str) -> Iterator[bytes]:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("note is not a regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                content = stream.read()
            yield content
            if not self._same_file(directory_fd, name, fd):
                raise OSError("note path changed during validation")
        finally:
            os.close(fd)

    @staticmethod
    def _same_file(directory_fd: int, name: str, file_fd: int) -> bool:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        held = os.fstat(file_fd)
        return (
            stat.S_ISREG(current.st_mode)
            and stat.S_ISREG(held.st_mode)
            and (current.st_dev, current.st_ino) == (held.st_dev, held.st_ino)
        )

    @staticmethod
    def _unlink(directory_fd: int, name: str) -> None:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            return
        os.fsync(directory_fd)

    @staticmethod
    def _same_directory(path: Path, directory_fd: int) -> bool:
        current = os.stat(path, follow_symlinks=False)
        held = os.fstat(directory_fd)
        return stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == (held.st_dev, held.st_ino)

    def _write(
        self, inbox: Path, inbox_fd: int, job: Job, action: NoteAction, now: datetime | None
    ) -> tuple[Path, str]:
        current = now or (datetime.fromisoformat(job.created_at) if job.created_at else datetime.now(UTC))
        encoded = self._render(job, action, current).encode("utf-8")
        identity_header = f'---\nrequest_id: "{job.request_id}"\n'.encode()
        for name in os.listdir(inbox_fd):
            if not name.endswith(".md"):
                continue
            content = None
            try:
                with self._read_regular(inbox_fd, name) as content:
                    if not content.startswith(identity_header):
                        continue
                    if content != encoded:
                        raise OSError("existing note content conflict")
            except OSError:
                if content is not None and content.startswith(identity_header):
                    raise
                continue
            os.fsync(inbox_fd)
            if not self._same_directory(inbox, inbox_fd):
                raise OSError("inbox directory changed during write")
            return self.config.inbox / name, hashlib.sha256(content).hexdigest()
        stem = slugify(action.title)
        existing_names = {unicodedata.normalize("NFC", name).casefold() for name in os.listdir(inbox_fd)}
        temp_name = f".note-{uuid.uuid4().hex}.tmp"
        fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=inbox_fd)
        installed: str | None = None
        try:
            os.fchmod(fd, 0o600)
            stream = os.fdopen(fd, "wb")
            fd = -1
            with stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            index = 1
            while installed is None:
                suffix = "" if index == 1 else f" ({index})"
                candidate = f"{stem}{suffix}.md"
                if candidate.casefold() in existing_names:
                    index += 1
                    continue
                try:
                    os.link(temp_name, candidate, src_dir_fd=inbox_fd, dst_dir_fd=inbox_fd)
                    installed = candidate
                except FileExistsError:
                    index += 1
            self._unlink(inbox_fd, temp_name)
            with self._read_regular(inbox_fd, installed) as verified:
                if verified != encoded:
                    self._unlink(inbox_fd, installed)
                    raise OSError("note read-back verification failed")
            os.fsync(inbox_fd)
            if not self._same_directory(inbox, inbox_fd):
                raise OSError("inbox directory changed during write")
            return self.config.inbox / installed, hashlib.sha256(verified).hexdigest()
        finally:
            if fd >= 0:
                os.close(fd)
            self._unlink(inbox_fd, temp_name)

    def _update_thread_index(self, thread_id: str, inbox_fd: int) -> None:
        directory = self.config.vault_dir / "Voice Threads"
        if directory.is_symlink():
            raise UnsafeWrite("Voice Threads must be a real directory, not a symlink")
        directory.mkdir(exist_ok=True)
        if not directory.is_dir() or directory.resolve() != directory.absolute():
            raise UnsafeWrite("Voice Threads must be a canonical vault directory")
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        name = f"{thread_id}.md"
        temp_name = f".thread-{uuid.uuid4().hex}.tmp"
        try:
            try:
                with self._read_regular(directory_fd, name) as existing:
                    text = existing.decode("utf-8")
                if not text.startswith(f'---\nthread_id: "{thread_id}"\n'):
                    raise OSError("existing thread index identity conflict")
            except FileNotFoundError:
                pass
            entries = []
            for member_name in os.listdir(inbox_fd):
                if not member_name.endswith(".md"):
                    continue
                try:
                    with self._read_regular(inbox_fd, member_name) as content:
                        member = content.decode("utf-8")
                except (OSError, UnicodeError):
                    continue
                if f'thread_id: "{thread_id}"\n' not in member:
                    continue
                request = re.search(r'^request_id: "([0-9a-f-]{36})"$', member, re.M)
                created = re.search(r'^created_at: "([^"]+)"$', member, re.M)
                summary = re.search(r'^> (.+)$', member, re.M)
                if not request or not created or not summary:
                    raise OSError(f"thread member metadata is incomplete: {member_name}")
                clean_summary = " ".join(summary[1].split())
                link = (self.config.inbox / Path(member_name).with_suffix("")).as_posix()
                line = f"- {created[1]} — [[{link}]] — {clean_summary} <!-- {request[1]} -->"
                entries.append((created[1], request[1], line))
            encoded = (
                f'---\nthread_id: "{thread_id}"\ntags: ["voice-thread"]\n---\n\n'
                "# Voice Thread\n\n## Notes\n\n" + "\n".join(x[2] for x in sorted(entries)) + "\n"
            ).encode("utf-8")
            fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
            try:
                with os.fdopen(fd, "wb") as stream:
                    fd = -1
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                os.fsync(directory_fd)
            finally:
                if fd >= 0:
                    os.close(fd)
                self._unlink(directory_fd, temp_name)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _render(job: Job, action: NoteAction, created: datetime) -> str:
        source_name = PurePath(job.original_filename.replace("\\", "/")).name
        tags = json.dumps(list(action.tags), ensure_ascii=False)
        return (
            "---\n"
            f'request_id: "{job.request_id}"\n'
            f'thread_id: "{job.thread_id}"\n'
            f'thread: "[[Voice Threads/{job.thread_id}|Voice thread]]"\n'
            f'created_at: "{created.astimezone(UTC).isoformat()}"\n'
            f'source_filename: {json.dumps(source_name, ensure_ascii=False)}\n'
            f'source_content_type: {json.dumps(job.content_type)}\n'
            f'source_bytes: {job.byte_count}\n'
            f'source_sha256: "{job.sha256}"\n'
            f'source_archive: {json.dumps(job.archive_path)}\n'
            f"tags: {tags}\n"
            "---\n\n"
            f"# {action.title}\n\n"
            f"> {action.summary}\n\n"
            f"{action.body}\n"
        )

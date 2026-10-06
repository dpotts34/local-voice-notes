from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import sqlite3
import stat
from contextlib import closing, contextmanager
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .spool import open_private_directory

TERMINAL_STATUSES = {"completed", "failed"}


class LeaseLost(RuntimeError):
    pass


class SpoolIntegrityError(RuntimeError):
    pass


class _Connection(sqlite3.Connection):
    _validated_fd = -1

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._validated_fd >= 0:
                os.close(self._validated_fd)
                self._validated_fd = -1


@dataclass(frozen=True, slots=True)
class Job:
    request_id: str
    thread_id: str
    sha256: str
    original_filename: str
    stored_filename: str
    content_type: str
    byte_count: int
    spool_path: str
    archive_path: str | None = None
    transcript_path: str | None = None
    note_path: str | None = None
    note_sha256: str | None = None
    status: str = "received"
    error_stage: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    claim_owner: str | None = None
    claim_expires_at: str | None = None
    notification_nonce: str | None = None
    notification_event_id: str | None = None
    notification_summary: str | None = None
    completed_at: str | None = None
    archive_deleted_at: str | None = None
    archive_delete_outcome: str | None = None


class JobStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    def _connect(self, *, create: bool = False) -> sqlite3.Connection:
        flags = os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            expected = os.lstat(self.path)
        except FileNotFoundError:
            if not create:
                raise OSError("database path is missing")
            try:
                fd = os.open(self.path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                expected = os.lstat(self.path)
                if not stat.S_ISREG(expected.st_mode):
                    raise OSError("database path is not a regular file")
                fd = os.open(self.path, flags)
            else:
                expected = os.fstat(fd)
        else:
            if not stat.S_ISREG(expected.st_mode):
                raise OSError("database path is not a regular file")
            fd = os.open(self.path, flags)
        connection = None
        try:
            opened = os.fstat(fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
            ):
                raise OSError("database path is not an owned regular file")
            expected_path = self.path.resolve(strict=True)
            connection = sqlite3.connect(
                f"file:/proc/self/fd/{fd}?mode=rw", timeout=10, uri=True, factory=_Connection
            )
            connection._validated_fd = fd
            fd = -1
            current = os.lstat(self.path)
            if (
                not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                raise OSError("database path changed during connection")
            database_path = connection.execute("PRAGMA database_list").fetchone()[2]
            if Path(database_path).resolve(strict=False) != expected_path:
                raise OSError("database path changed during connection")
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            return connection
        except BaseException:
            if connection is not None:
                connection.close()
            raise
        finally:
            if fd >= 0:
                os.close(fd)

    def _initialize(self) -> None:
        with closing(self._connect(create=True)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    request_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL, sha256 TEXT NOT NULL,
                    original_filename TEXT NOT NULL, stored_filename TEXT NOT NULL,
                    content_type TEXT NOT NULL, byte_count INTEGER NOT NULL,
                    spool_path TEXT NOT NULL, archive_path TEXT, transcript_path TEXT,
                    note_path TEXT, status TEXT NOT NULL, error_stage TEXT,
                    error_message TEXT, retry_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)
            existing = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            migrations = {
                "claim_owner": "TEXT",
                "claim_expires_at": "TEXT",
                "notification_nonce": "TEXT",
                "notification_event_id": "TEXT",
                "notification_summary": "TEXT",
                "note_sha256": "TEXT",
                "completed_at": "TEXT",
                "archive_deleted_at": "TEXT",
                "archive_delete_outcome": "TEXT",
            }
            for column, kind in migrations.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {kind}")

    def create_or_get(self, job: Job) -> tuple[Job, bool]:
        now = datetime.now(UTC).isoformat()
        stored = replace(job, created_at=job.created_at or now, updated_at=job.updated_at or now)
        columns = [field.name for field in fields(Job)]
        values = [getattr(stored, column) for column in columns]
        with closing(self._connect()) as db, db:
            cursor = db.execute(
                f"INSERT OR IGNORE INTO jobs ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            created = cursor.rowcount == 1
            row = db.execute("SELECT * FROM jobs WHERE request_id = ?", (job.request_id,)).fetchone()
        return self._row(row), created

    def install_spool_and_create(self, job: Job, incoming: Path, final: Path) -> tuple[Job, bool]:
        """Serialize file installation and row creation under SQLite's cross-process write lock."""
        now = datetime.now(UTC).isoformat()
        stored = replace(job, spool_path=str(final), created_at=job.created_at or now, updated_at=job.updated_at or now)
        columns = [field.name for field in fields(Job)]
        values = [getattr(stored, column) for column in columns]
        installed = False
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT * FROM jobs WHERE request_id = ?", (job.request_id,)).fetchone()
                if row is not None:
                    existing = self._row(row)
                    self._verify_spool(existing)
                    db.commit()
                    return existing, False
                if incoming.parent != final.parent:
                    raise OSError("spool directory changed before installation")
                directory_fd = open_private_directory(final.parent, label="spool")
                try:
                    try:
                        os.unlink(final.name, dir_fd=directory_fd)  # orphan from a process that died before commit
                        os.fsync(directory_fd)
                    except FileNotFoundError:
                        pass
                    os.link(
                        incoming.name, final.name,
                        src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                    installed = True
                    os.fsync(directory_fd)
                    db.execute(
                        f"INSERT INTO jobs ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values
                    )
                    db.commit()
                    return stored, True
                except BaseException:
                    db.rollback()
                    if installed:
                        try:
                            os.unlink(final.name, dir_fd=directory_fd)
                            os.fsync(directory_fd)
                        except FileNotFoundError:
                            pass
                    raise
                finally:
                    os.close(directory_fd)
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _verify_spool(job: Job) -> None:
        path = Path(job.spool_path)
        directory_fd = -1
        try:
            directory_fd = open_private_directory(path.parent, label="spool")
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(
                os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd),
                "rb",
            ) as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise SpoolIntegrityError("authoritative spool integrity conflict")
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
        except OSError as error:
            raise SpoolIntegrityError("authoritative spool integrity conflict") from error
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)
        if size != job.byte_count or digest.hexdigest() != job.sha256:
            raise SpoolIntegrityError("authoritative spool integrity conflict")

    def get(self, request_id: str) -> Job | None:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM jobs WHERE request_id = ?", (request_id,)).fetchone()
        return self._row(row) if row else None

    def is_operable(self) -> bool:
        try:
            with closing(self._connect()) as db:
                row = db.execute("PRAGMA quick_check").fetchone()
            return row is not None and row[0] == "ok"
        except (OSError, sqlite3.Error):
            return False

    def transition(self, request_id: str, status: str, *, owner: str | None = None, **updates: Any) -> Job:
        allowed = {field.name for field in fields(Job)} - {"request_id", "created_at"}
        if not set(updates) <= allowed:
            raise ValueError("unknown job field")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            now = datetime.now(UTC).isoformat()
            updates = {"status": status, "updated_at": now, **updates}
            if status == "completed":
                updates.setdefault("completed_at", now)
            if status in TERMINAL_STATUSES:
                updates.update(claim_owner=None, claim_expires_at=None)
            assignments = ", ".join(f"{key} = ?" for key in updates)
            where = "request_id = ?"
            params: tuple[Any, ...] = (*updates.values(), request_id)
            if owner is not None:
                where += " AND claim_owner = ? AND claim_expires_at > ?"
                params += (owner, now)
            cursor = db.execute(f"UPDATE jobs SET {assignments} WHERE {where}", params)
            if owner is not None and cursor.rowcount != 1:
                raise LeaseLost("worker lease was lost")
        job = self.get(request_id)
        if job is None:
            raise KeyError(request_id)
        return job

    def record_failure(
        self, request_id: str, stage: str, message: str, *, owner: str | None = None,
        max_retries: int | None = None,
    ) -> Job:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            now = datetime.now(UTC).isoformat()
            terminal = (
                "status = CASE WHEN retry_count + 1 >= ? THEN 'failed' ELSE status END, "
                if max_retries is not None else ""
            )
            params: list[Any] = [stage, message[:2000], now]
            if max_retries is not None:
                params.insert(0, max_retries)
            where = "request_id = ?"
            params.append(request_id)
            if owner is not None:
                where += " AND claim_owner = ? AND claim_expires_at > ?"
                params.extend((owner, now))
            cursor = db.execute(
                f"UPDATE jobs SET {terminal}error_stage = ?, error_message = ?, retry_count = retry_count + 1, "
                "updated_at = ?, claim_owner = NULL, claim_expires_at = NULL WHERE " + where,
                params,
            )
            if cursor.rowcount != 1:
                if owner is not None:
                    raise LeaseLost("worker lease was lost")
                raise KeyError(request_id)
            row = db.execute("SELECT * FROM jobs WHERE request_id = ?", (request_id,)).fetchone()
        return self._row(row)

    def assert_claim(self, request_id: str, owner: str) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT 1 FROM jobs WHERE request_id = ? AND claim_owner = ? AND claim_expires_at > ?",
                (request_id, owner, now),
            ).fetchone()
        if row is None:
            raise LeaseLost("worker lease was lost")

    def ensure_notification_nonce(self, request_id: str, owner: str) -> str:
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            now = datetime.now(UTC).isoformat()
            row = db.execute(
                "SELECT notification_nonce FROM jobs WHERE request_id = ? AND claim_owner = ? "
                "AND claim_expires_at > ?", (request_id, owner, now),
            ).fetchone()
            if row is None:
                db.rollback()
                raise LeaseLost("worker lease was lost")
            nonce = row["notification_nonce"]
            if nonce is None:
                nonce = secrets.token_hex(32)
                db.execute(
                    "UPDATE jobs SET notification_nonce = ?, updated_at = ? WHERE request_id = ?",
                    (nonce, now, request_id),
                )
            db.commit()
        return nonce

    @contextmanager
    def claimed_effect(self, request_id: str, owner: str, lease_seconds: int) -> Iterator[None]:
        self.assert_claim(request_id, owner)
        if not self.renew_claim(request_id, owner, lease_seconds):
            raise LeaseLost("worker lease was lost")
        cancelled = False
        try:
            yield
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if not cancelled and not self.renew_claim(request_id, owner, lease_seconds):
                raise LeaseLost("worker lease was lost")

    def list_jobs(self) -> list[Job]:
        with closing(self._connect()) as db, db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()
        return [self._row(row) for row in rows]

    def recent_threads(self, limit: int) -> list[dict[str, Any]]:
        with closing(self._connect()) as db, db:
            rows = db.execute("""
                WITH ranked AS (
                    SELECT *,
                           COUNT(*) OVER (PARTITION BY thread_id) AS recording_count,
                           ROW_NUMBER() OVER (
                               PARTITION BY thread_id ORDER BY created_at DESC, request_id DESC
                           ) AS position
                    FROM jobs
                )
                SELECT thread_id,
                       request_id AS latest_request_id,
                       recording_count,
                       status AS latest_status,
                       updated_at,
                       SUBSTR(COALESCE(notification_summary, original_filename), 1, 80) AS preview
                FROM ranked
                WHERE position = 1
                ORDER BY created_at DESC, request_id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(row) for row in rows]

    def recoverable(self, max_retries: int | None = None) -> list[Job]:
        with closing(self._connect()) as db, db:
            if max_retries is not None:
                now = datetime.now(UTC).isoformat()
                db.execute(
                    "UPDATE jobs SET status = 'failed', claim_owner = NULL, claim_expires_at = NULL, updated_at = ? "
                    "WHERE status NOT IN ('completed','failed') AND retry_count >= ?",
                    (now, max_retries),
                )
            rows = db.execute(
                "SELECT * FROM jobs WHERE status NOT IN ('completed','failed') "
                "OR (status = 'failed' AND notification_event_id IS NULL) "
                "ORDER BY status = 'failed', created_at"
            ).fetchall()
        return [self._row(row) for row in rows]

    def claim_next(
        self, owner: str, lease_seconds: int, max_retries: int | None = None, *, now: datetime | None = None
    ) -> Job | None:
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            current = now or datetime.now(UTC)
            expiry = (current + timedelta(seconds=lease_seconds)).isoformat()
            params: list[Any] = [current.isoformat()]
            retry_clause = ""
            if max_retries is not None:
                retry_clause = " AND retry_count < ?"
                params.append(max_retries)
            if max_retries is not None:
                db.execute(
                    "UPDATE jobs SET status = 'failed', claim_owner = NULL, claim_expires_at = NULL, updated_at = ? "
                    "WHERE status NOT IN ('completed','failed') AND retry_count >= ?",
                    (current.isoformat(), max_retries),
                )
            row = db.execute(
                "SELECT request_id, status, notification_nonce FROM jobs "
                "WHERE (claim_owner IS NULL OR claim_expires_at <= ?) AND "
                "((status NOT IN ('completed','failed')" + retry_clause + ") "
                "OR (status = 'failed' AND notification_event_id IS NULL)) "
                "ORDER BY status = 'failed', created_at LIMIT 1",
                params,
            ).fetchone()
            if row is None:
                db.commit()
                return None
            nonce = secrets.token_hex(32) if row["status"] == "failed" and row["notification_nonce"] is None else None
            db.execute(
                "UPDATE jobs SET claim_owner = ?, claim_expires_at = ?, updated_at = ?, "
                "notification_nonce = COALESCE(notification_nonce, ?) WHERE request_id = ?",
                (owner, expiry, current.isoformat(), nonce, row["request_id"]),
            )
            claimed = db.execute("SELECT * FROM jobs WHERE request_id = ?", (row["request_id"],)).fetchone()
            db.commit()
        return self._row(claimed)

    def renew_claim(self, request_id: str, owner: str, lease_seconds: int) -> bool:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = datetime.now(UTC)
            expiry = (current + timedelta(seconds=lease_seconds)).isoformat()
            cursor = db.execute(
                "UPDATE jobs SET claim_expires_at = ? WHERE request_id = ? AND claim_owner = ? "
                "AND claim_expires_at IS NOT NULL AND claim_expires_at > ?",
                (expiry, request_id, owner, current.isoformat()),
            )
        return cursor.rowcount == 1

    def release_claim(self, request_id: str, owner: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE jobs SET claim_owner = NULL, claim_expires_at = NULL WHERE request_id = ? AND claim_owner = ?",
                (request_id, owner),
            )

    @staticmethod
    def _require_same_directory(path: Path, directory_fd: int) -> None:
        current = os.stat(path, follow_symlinks=False)
        held = os.fstat(directory_fd)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise OSError("archive directory changed during retention")

    @classmethod
    def _delete_archive(cls, row: sqlite3.Row, archive_dir: Path) -> str:
        path = Path(row["archive_path"])
        if archive_dir != archive_dir.resolve(strict=True):
            raise OSError("archive retention root conflict")
        if path.parent != archive_dir or path.name != row["stored_filename"]:
            raise OSError("archive retention path conflict")
        directory_fd = os.open(archive_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            cls._require_same_directory(archive_dir, directory_fd)
            try:
                fd = os.open(
                    row["stored_filename"], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except FileNotFoundError:
                os.fsync(directory_fd)
                cls._require_same_directory(archive_dir, directory_fd)
                return "missing"
            except OSError as error:
                raise OSError("archive retention object conflict") from error
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode):
                    raise OSError("archive retention object conflict")
                digest = hashlib.sha256()
                size = 0
                with os.fdopen(fd, "rb") as stream:
                    fd = -1
                    while chunk := stream.read(1024 * 1024):
                        size += len(chunk)
                        digest.update(chunk)
                if size != row["byte_count"] or digest.hexdigest() != row["sha256"]:
                    raise OSError("archive retention content conflict")
                current = os.stat(row["stored_filename"], dir_fd=directory_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                    raise OSError("archive retention object changed")
                cls._require_same_directory(archive_dir, directory_fd)
                os.unlink(row["stored_filename"], dir_fd=directory_fd)
                os.fsync(directory_fd)
                cls._require_same_directory(archive_dir, directory_fd)
                return "deleted"
            finally:
                if fd >= 0:
                    os.close(fd)
        finally:
            os.close(directory_fd)

    def enforce_archive_retention(self, cap_bytes: int, archive_dir: Path) -> list[tuple[str, str]]:
        if cap_bytes < 0:
            raise ValueError("archive retention cap cannot be negative")
        events: list[tuple[str, str]] = []
        with closing(self._connect()) as db:
            pending = db.execute(
                "SELECT * FROM jobs WHERE archive_path IS NOT NULL AND archive_deleted_at IS NULL "
                "AND archive_delete_outcome = 'deleting' "
                "ORDER BY completed_at, created_at, request_id"
            ).fetchall()
            pending_ids = {row["request_id"] for row in pending}
            for row in pending:
                try:
                    outcome = self._delete_archive(row, archive_dir)
                except OSError as error:
                    now = datetime.now(UTC).isoformat()
                    with db:
                        db.execute(
                            "UPDATE jobs SET error_stage = 'retention', error_message = ?, updated_at = ? "
                            "WHERE request_id = ?",
                            (f"retention conflict: {error}", now, row["request_id"]),
                        )
                    events.append((row["request_id"], "conflict"))
                    continue
                if outcome == "missing":
                    outcome = "deleted"
                deleted_at = datetime.now(UTC).isoformat()
                with db:
                    db.execute(
                        "UPDATE jobs SET archive_deleted_at = ?, archive_delete_outcome = ?, "
                        "error_stage = NULL, error_message = NULL, updated_at = ? WHERE request_id = ?",
                        (deleted_at, outcome, deleted_at, row["request_id"]),
                    )
                events.append((row["request_id"], outcome))
            rows = db.execute(
                "SELECT * FROM jobs WHERE status = 'completed' AND archive_path IS NOT NULL "
                "AND archive_deleted_at IS NULL ORDER BY completed_at, created_at, request_id"
            ).fetchall()
            usage = sum(row["byte_count"] for row in rows)
            for row in rows:
                if usage <= cap_bytes:
                    break
                if row["request_id"] in pending_ids:
                    continue
                marked_at = datetime.now(UTC).isoformat()
                with db:
                    db.execute(
                        "UPDATE jobs SET archive_delete_outcome = 'deleting', updated_at = ? "
                        "WHERE request_id = ? AND archive_deleted_at IS NULL",
                        (marked_at, row["request_id"]),
                    )
                try:
                    outcome = self._delete_archive(row, archive_dir)
                except OSError as error:
                    now = datetime.now(UTC).isoformat()
                    with db:
                        db.execute(
                            "UPDATE jobs SET error_stage = 'retention', error_message = ?, updated_at = ? "
                            "WHERE request_id = ?",
                            (f"retention conflict: {error}", now, row["request_id"]),
                        )
                    events.append((row["request_id"], "conflict"))
                    continue
                deleted_at = datetime.now(UTC).isoformat()
                with db:
                    db.execute(
                        "UPDATE jobs SET archive_deleted_at = ?, archive_delete_outcome = ?, "
                        "error_stage = NULL, error_message = NULL, updated_at = ? WHERE request_id = ?",
                        (deleted_at, outcome, deleted_at, row["request_id"]),
                    )
                usage -= row["byte_count"]
                events.append((row["request_id"], outcome))
        return events

    @staticmethod
    def _row(row: sqlite3.Row) -> Job:
        return Job(**dict(row))

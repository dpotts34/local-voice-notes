from __future__ import annotations

import hashlib
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator


@dataclass(frozen=True, slots=True)
class SpoolResult:
    path: Path
    sha256: str
    byte_count: int


class EmptyUpload(ValueError):
    pass


class UploadTooLarge(ValueError):
    pass


def open_private_directory(directory: Path, *, create: bool = False, label: str = "state") -> int:
    created = False
    if create and not os.path.lexists(directory):
        existing_parent = directory.parent
        while not os.path.lexists(existing_parent):
            existing_parent = existing_parent.parent
        parent_stat = os.stat(existing_parent, follow_symlinks=False)
        if existing_parent != existing_parent.resolve(strict=True) or not stat.S_ISDIR(parent_stat.st_mode):
            raise OSError(f"{label} directory parent must be canonical and non-symlink")
        directory.mkdir(parents=True, mode=0o700)
        created = True
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as error:
        raise OSError(f"{label} directory must be a real non-symlink directory") from error
    try:
        held = os.fstat(fd)
        current = os.stat(directory, follow_symlinks=False)
        if created:
            if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
                raise OSError(f"{label} directory changed during creation")
            os.fchmod(fd, 0o700)
            held = os.fstat(fd)
        if (
            directory != directory.resolve(strict=True)
            or not stat.S_ISDIR(current.st_mode)
            or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise OSError(f"{label} directory must be an exact canonical non-symlink directory")
        if held.st_uid != os.geteuid() or stat.S_IMODE(held.st_mode) & 0o077:
            raise OSError(f"{label} directory must be private and owned by the service user")
        return fd
    except BaseException:
        os.close(fd)
        raise


def private_directory_available(directory: Path) -> bool:
    try:
        fd = open_private_directory(directory)
    except OSError:
        return False
    os.close(fd)
    return True


def _fsync_directory(directory: Path) -> None:
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def durable_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


async def spool_stream(chunks: AsyncIterator[bytes], directory: Path, final_name: str, limit: int) -> SpoolResult:
    if Path(final_name).name != final_name:
        raise ValueError("spool filename must be a basename")
    directory_fd = open_private_directory(directory, create=True, label="spool")
    temporary = f".upload-{uuid.uuid4().hex}"
    fd = -1
    digest = hashlib.sha256()
    size = 0
    installed = False
    try:
        fd = os.open(
            temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd,
        )
        target = os.fdopen(fd, "wb")
        fd = -1
        with target:
            os.fchmod(target.fileno(), 0o600)
            async for chunk in chunks:
                size += len(chunk)
                if size > limit:
                    raise UploadTooLarge("audio exceeds configured limit")
                target.write(chunk)
                digest.update(chunk)
            if size == 0:
                raise EmptyUpload("audio is empty")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, final_name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        installed = True
        os.fsync(directory_fd)
        return SpoolResult(directory / final_name, digest.hexdigest(), size)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except FileNotFoundError:
            pass
        if installed:
            try:
                os.unlink(final_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(directory_fd)

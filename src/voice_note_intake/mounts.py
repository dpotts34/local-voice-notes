from __future__ import annotations

import os
import stat
from pathlib import Path


def _unescape_mount_field(value: str) -> str:
    for escaped, literal in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        value = value.replace(escaped, literal)
    return value


def is_nfs_mount(path: Path, mountinfo_path: Path = Path("/proc/self/mountinfo")) -> bool:
    target = os.path.abspath(path)
    try:
        lines = mountinfo_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        fields = line.split()
        try:
            separator = fields.index("-")
            mountpoint = _unescape_mount_field(fields[4])
            filesystem = fields[separator + 1]
        except (ValueError, IndexError):
            continue
        if mountpoint == target and filesystem in {"nfs", "nfs4"}:
            return True
    return False


def archive_available(path: Path, require_nfs: bool) -> tuple[bool, dict[str, bool]]:
    try:
        resolved = path.resolve(strict=True)
        current = os.stat(path, follow_symlinks=False)
        resolved_current = os.stat(resolved, follow_symlinks=False)
        usable = (
            resolved == path.absolute()
            and stat.S_ISDIR(current.st_mode)
            and (current.st_dev, current.st_ino) == (resolved_current.st_dev, resolved_current.st_ino)
            and os.access(path, os.R_OK | os.W_OK | os.X_OK)
        )
    except OSError:
        usable = False
    mounted = is_nfs_mount(path) if require_nfs else True
    return usable and mounted, {"usable": usable, "nfs_mount": mounted, "nfs_required": require_nfs}

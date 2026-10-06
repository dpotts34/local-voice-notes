from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePath


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"{name} must be a boolean")
    return normalized in {"true", "1", "yes"}


@dataclass(frozen=True, slots=True)
class Config:
    state_dir: Path
    archive_dir: Path
    vault_dir: Path
    inbox: Path
    bind_host: str
    bind_port: int
    asr_url: str
    llm_url: str
    llm_model: str
    llm_fallback_url: str | None
    llm_fallback_model: str | None
    llm_primary_timeout_seconds: float
    llm_fallback_timeout_seconds: float
    ntfy_url: str
    max_upload_bytes: int
    http_timeout_seconds: float
    max_retries: int
    require_nfs_mount: bool
    archive_max_bytes: int
    vault_sync: bool = False
    vault_repo_dir: Path | None = None
    vault_remote: str | None = None
    vault_branch: str = "main"
    vault_git_ssh_key: Path | None = None

    @classmethod
    def from_env(cls) -> "Config":
        sync = _env_bool("VOICE_VAULT_SYNC", False)
        repo = Path(_required("VOICE_VAULT_REPO_DIR")) if sync else None
        remote = _required("VOICE_VAULT_REMOTE") if sync else None
        inbox_raw = os.environ.get("VOICE_INBOX", "Voice Inbox")
        inbox = Path(inbox_raw)
        parts = PurePath(inbox_raw).parts
        if (
            inbox != Path("Voice Inbox")
            or inbox.is_absolute()
            or not parts
            or inbox_raw == "."
            or any(p in {"..", ""} for p in parts)
        ):
            raise ValueError("VOICE_INBOX must be exactly the safe vault-relative path 'Voice Inbox'")
        return cls(
            state_dir=_env_path("VOICE_STATE_DIR", str(Path.home() / ".local/state/voice-note-intake")),
            archive_dir=Path(_required("VOICE_ARCHIVE_DIR")).expanduser(),
            vault_dir=Path(_required("VOICE_VAULT_DIR")).expanduser(),
            inbox=inbox,
            bind_host=os.environ.get("VOICE_BIND_HOST", "127.0.0.1"),
            bind_port=int(os.environ.get("VOICE_BIND_PORT", "8791")),
            asr_url=_required("VOICE_ASR_URL"),
            llm_url=_required("VOICE_LLM_URL"),
            llm_model=_required("VOICE_LLM_MODEL"),
            llm_fallback_url=os.environ.get("VOICE_LLM_FALLBACK_URL") or None,
            llm_fallback_model=os.environ.get("VOICE_LLM_FALLBACK_MODEL") or None,
            llm_primary_timeout_seconds=float(os.environ.get("VOICE_LLM_PRIMARY_TIMEOUT", "30")),
            llm_fallback_timeout_seconds=float(os.environ.get("VOICE_LLM_FALLBACK_TIMEOUT", "180")),
            ntfy_url=_required("VOICE_NTFY_URL"),
            max_upload_bytes=int(os.environ.get("VOICE_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))),
            http_timeout_seconds=float(os.environ.get("VOICE_HTTP_TIMEOUT", "30")),
            max_retries=int(os.environ.get("VOICE_MAX_RETRIES", "3")),
            require_nfs_mount=_env_bool("VOICE_REQUIRE_NFS_MOUNT", False),
            archive_max_bytes=int(os.environ.get("VOICE_ARCHIVE_MAX_BYTES", str(5 * 1024**3))),
            vault_sync=sync, vault_repo_dir=repo, vault_remote=remote,
            vault_branch=os.environ.get("VOICE_VAULT_BRANCH", "main"),
            vault_git_ssh_key=Path(os.environ["VOICE_VAULT_GIT_SSH_KEY"])
            if sync and os.environ.get("VOICE_VAULT_GIT_SSH_KEY") else None,
        )

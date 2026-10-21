from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from voice_note_intake.config import Config
from voice_note_intake import vault_sync
from voice_note_intake.main import WORKER_KEY, create_app


class RecordedSync:
    calls = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.calls.append((args, kwargs))

    def run(self, message="Sync voice notes"):
        self.message = message


def config(tmp_path: Path) -> Config:
    return Config(
        state_dir=tmp_path / "state", archive_dir=tmp_path / "archive",
        vault_dir=tmp_path / "vault", inbox=Path("Voice Inbox"),
        bind_host="127.0.0.1", bind_port=8791, asr_url="http://asr",
        llm_url="http://llm", llm_model="test", llm_fallback_url=None,
        llm_fallback_model=None, llm_primary_timeout_seconds=30,
        llm_fallback_timeout_seconds=180, ntfy_url="http://ntfy",
        max_upload_bytes=100, http_timeout_seconds=30, max_retries=3,
        require_nfs_mount=False, archive_max_bytes=1000, vault_sync=True,
        vault_repo_dir=tmp_path / "repo", vault_remote="https://example.invalid/vault.git",
        vault_branch="private-branch", vault_git_ssh_key=None,
    )


def install_factory(monkeypatch, expression: str):
    module = types.ModuleType("test_sync_factory_plugin")
    setattr(module, "make_sync", RecordedSync)
    setattr(module, "not_callable", "not a factory")
    sys.modules[module.__name__] = module
    monkeypatch.setenv("VOICE_VAULT_SYNC_FACTORY", expression)
    return module


def test_default_factory_is_used_by_app_and_cli(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    monkeypatch.delenv("VOICE_VAULT_SYNC_FACTORY", raising=False)
    monkeypatch.setattr(vault_sync, "VaultSync", RecordedSync)
    cfg.vault_dir.mkdir(parents=True)
    cfg.vault_repo_dir.mkdir()
    RecordedSync.calls.clear()
    app = create_app(cfg)
    syncer = app[WORKER_KEY].syncer
    assert isinstance(syncer, RecordedSync)
    assert syncer.kwargs == {
        "vault": cfg.vault_dir, "state_dir": cfg.state_dir, "repo": cfg.vault_repo_dir,
        "remote": cfg.vault_remote, "branch": cfg.vault_branch,
        "ssh_key": cfg.vault_git_ssh_key,
    }

    monkeypatch.setattr(Config, "from_env", classmethod(lambda cls: cfg))
    monkeypatch.setattr(sys, "argv", ["voice-note-vault-sync"])
    vault_sync.main()
    assert len(RecordedSync.calls) == 2
    assert RecordedSync.calls[-1] == ((), syncer.kwargs)


def test_custom_factory_is_used_by_app_and_cli(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    install_factory(monkeypatch, "test_sync_factory_plugin:make_sync")
    RecordedSync.calls.clear()
    app = create_app(cfg)
    assert isinstance(app[WORKER_KEY].syncer, RecordedSync)
    monkeypatch.setattr(Config, "from_env", classmethod(lambda cls: cfg))
    monkeypatch.setattr(sys, "argv", ["voice-note-vault-sync"])
    vault_sync.main()
    assert len(RecordedSync.calls) == 2


@pytest.mark.parametrize("expression", [
    "bad", "no_such_module:make", "test_sync_factory_plugin:missing",
    "test_sync_factory_plugin:not_callable",
])
def test_invalid_factory_fails_clearly_in_both_paths(tmp_path, monkeypatch, expression):
    cfg = config(tmp_path)
    monkeypatch.setattr(vault_sync, "VaultSync", RecordedSync)
    monkeypatch.setenv("VOICE_VAULT_SYNC_FACTORY", expression)
    with pytest.raises(ValueError, match="VOICE_VAULT_SYNC_FACTORY"):
        create_app(cfg)

    monkeypatch.setattr(Config, "from_env", classmethod(lambda cls: cfg))
    monkeypatch.setattr(sys, "argv", ["voice-note-vault-sync"])
    with pytest.raises(SystemExit) as exit_info:
        vault_sync.main()
    assert exit_info.value.code == 1

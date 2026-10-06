#!/usr/bin/env python3
"""Installed HTTP acceptance: controlled regressions or opt-in real ASR/LLM."""
from __future__ import annotations

import argparse
import hashlib
import http.server
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

TRANSCRIPT = "Controlled fixture transcript: please remember the library books."
ACTION = {
    "title": "Controlled library reminder",
    "body": "Remember to return the library books.",
    "tags": ["reminder", "controlled-e2e"],
    "summary": "Return the library books.",
}
CHECKS: list[str] = []
OBSERVATIONS: list[dict[str, Any]] = []
VALIDATOR_CASES: list[dict[str, Any]] = []
SYNC_CASES: list[dict[str, Any]] = []


class FixtureState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.audio: bytes | None = None
        self.transcript_seen = False
        self.notification: dict[str, Any] | None = None
        self.asr_entered = threading.Event()
        self.asr_release = threading.Event()
        self.asr_fail = False
        self.llm_fail = False
        self.action_content = json.dumps(ACTION)
        self.notify_failures = 0
        self.notify_accept_then_fail = False
        self.events: list[dict[str, Any]] = []
        self.calls = {"asr": 0, "llm": 0, "notify": 0}
        self.before_notify = None


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ControlledVoiceFixture/1"

    @property
    def state(self) -> FixtureState:
        return self.server.fixture_state  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: object) -> None:
        pass

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/notify/json":
            self._send(404, b"{}")
            return
        with self.state.lock:
            body = "".join(json.dumps(event) + "\n" for event in self.state.events).encode()
        self._send(200, body, "application/x-ndjson")

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 12 * 1024 * 1024:
                self._send(400, b"{}")
                return
            body = self.rfile.read(length)
            if self.path == "/asr":
                content_type = self.headers.get("Content-Type", "")
                message = BytesParser(policy=policy.default).parsebytes(
                    f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
                )
                audio = None
                if message.is_multipart():
                    for part in message.iter_parts():
                        if part.get_param("name", header="content-disposition") == "file":
                            audio = part.get_payload(decode=True)
                            break
                if not audio:
                    self._send(400, b"{}")
                    return
                with self.state.lock:
                    self.state.audio = audio
                self.state.asr_entered.set()
                if not self.state.asr_release.wait(timeout=30):
                    self._send(503, b"{}")
                    return
                with self.state.lock:
                    self.state.calls["asr"] += 1
                    unavailable = self.state.asr_fail
                self._send(503 if unavailable else 200,
                           b"{}" if unavailable else json.dumps({"text": TRANSCRIPT}).encode())
                return
            if self.path == "/llm":
                request = json.loads(body)
                messages = request.get("messages", [])
                transcript_seen = any(
                    item.get("role") == "user" and TRANSCRIPT in item.get("content", "")
                    for item in messages if isinstance(item, dict)
                )
                if request.get("model") != "controlled-model" or not transcript_seen:
                    self._send(400, b"{}")
                    return
                with self.state.lock:
                    self.state.transcript_seen = True
                    self.state.calls["llm"] += 1
                    unavailable = self.state.llm_fail
                    content = self.state.action_content
                if unavailable:
                    self._send(503, b"{}")
                    return
                response = {"choices": [{"message": {"content": content}}]}
                self._send(200, json.dumps(response).encode())
                return
            if self.path == "/notify":
                if self.state.before_notify is not None:
                    self.state.before_notify(body)
                with self.state.lock:
                    self.state.calls["notify"] += 1
                    unavailable = self.state.notify_failures > 0
                    if unavailable:
                        self.state.notify_failures -= 1
                    accepted_failure = self.state.notify_accept_then_fail
                    self.state.notify_accept_then_fail = False
                if unavailable:
                    self._send(503, b"{}")
                    return
                event = {
                    "event": "message",
                    "id": f"controlled-event-{len(self.state.events) + 1}",
                    "title": self.headers.get("Title", ""),
                    "message": body.decode("utf-8"),
                    "tags": [tag for tag in self.headers.get("Tags", "").split(",") if tag],
                }
                with self.state.lock:
                    self.state.notification = event
                    self.state.events.append(event)
                self._send(503 if accepted_failure else 200, json.dumps({"id": event["id"]}).encode())
                return
            self._send(404, b"{}")
        except (BrokenPipeError, ConnectionResetError):
            pass  # The interruption scenario deliberately disconnects a pending ASR request.
        except Exception:
            self._send(500, b"{}")


class FixtureServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, state: FixtureState) -> None:
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.fixture_state = state
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=2)


def mark(name: str) -> None:
    CHECKS.append(name)


def clean_env(home: Path, path: str) -> dict[str, str]:
    return {
        "HOME": str(home),
        "PATH": path,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "C.UTF-8",
    }


def request_json(url: str, *, method: str = "GET", body: bytes | None = None,
                 headers: dict[str, str] | None = None, timeout: float = 5) -> tuple[int, Any]:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw.decode("utf-8", "replace")
        return error.code, payload


def make_audio() -> bytes:
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\0\0" * 1_600)
    return target.getvalue()


def multipart(audio: bytes, request_id: str) -> tuple[str, bytes]:
    boundary = "voice-note-e2e-" + uuid.uuid4().hex
    parts = [
        ("audio", "controlled.wav", "audio/wav", audio),
        ("request_id", None, "text/plain; charset=utf-8", request_id.encode()),
        ("thread_id", None, "text/plain; charset=utf-8", request_id.encode()),
    ]
    output = bytearray()
    for name, filename, content_type, value in parts:
        output.extend(f"--{boundary}\r\n".encode())
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        output.extend((disposition + "\r\n").encode())
        output.extend((f"Content-Type: {content_type}\r\n\r\n").encode())
        output.extend(value + b"\r\n")
    output.extend(f"--{boundary}--\r\n".encode())
    return boundary, bytes(output)


def submit(base: str, audio: bytes, request_id: str | None = None) -> dict[str, Any]:
    request_id = request_id or str(uuid.uuid4())
    boundary, payload = multipart(audio, request_id)
    status, job = request_json(base + "/v1/voice-notes", method="POST", body=payload,
                              headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    if status != 202 or job.get("request_id") != request_id:
        raise RuntimeError("scenario upload did not receive durable HTTP 202")
    return job


def wait_job(base: str, request_id: str, predicate, description: str,
             timeout: float = 20) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    job: Any = None
    while time.monotonic() < deadline:
        status, job = request_json(base + "/v1/jobs/" + request_id)
        if status == 200 and isinstance(job, dict) and predicate(job):
            OBSERVATIONS.append({"scenario": description, "request_id": request_id,
                                 **{k: job.get(k) for k in (
                                     "status", "retry_count", "error_stage", "sha256",
                                     "note_path", "notification_event_id", "archive_delete_outcome")}})
            return job
        time.sleep(0.1)
    raise RuntimeError(f"{description}: bounded job poll failed; last HTTP job={job}")


def allocate_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def check_vault(executable: Path, vault: Path, root: Path) -> None:
    validator = executable.with_name("voice-vault-lint")
    env = clean_env(root / "home", str(executable.parent) + os.pathsep + os.defpath)
    if not validator.is_file() or not os.access(validator, os.X_OK):
        raise RuntimeError("installed voice-vault-lint executable is missing or not executable")
    original = {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*.md")}

    def invoke(name: str, arguments: list[str], code: int, reason: str) -> None:
        result = subprocess.run([str(validator), *arguments], cwd=root, env=env,
                                capture_output=True, text=True, timeout=5)
        output = result.stdout + result.stderr
        VALIDATOR_CASES.append({"case": name, "returncode": result.returncode,
                                "output": output.replace(str(root), "<disposable>")})
        if result.returncode != code or reason not in output:
            raise RuntimeError(f"vault validation case {name!r}: expected exit {code} and {reason!r}; {output}")
        if any((vault / relative).read_bytes() != content for relative, content in original.items()):
            raise RuntimeError("read-only validator changed an existing generated note")
        mark("installed vault validation: " + name)

    arguments = ["--vault", str(vault)]
    invoke("differently named canonical vault and generated notes", arguments, 0, "0 findings")
    invoke("missing explicit boundary", [], 2, "--vault")
    for name, boundary in (
        ("relative boundary", vault.name),
        ("traversal boundary", str(vault / ".." / vault.name)),
        ("nonexistent boundary", str(root / "missing-vault")),
        ("file boundary", str(next(vault.rglob("*.md")))),
        ("filesystem root boundary", "/"),
    ):
        invoke(name, ["--vault", boundary], 2, "canonical")
    linked_root = root / "linked-vault"
    linked_root.symlink_to(vault, target_is_directory=True)
    invoke("symlink boundary", ["--vault", str(linked_root)], 2, "canonical")
    linked_parent = root / "linked-parent"
    linked_parent.symlink_to(root, target_is_directory=True)
    invoke("symlink ancestor", ["--vault", str(linked_parent / vault.name)], 2, "canonical")
    for selector in (str(root / "outside.md"), "../outside.md"):
        invoke("refuse note selector " + ("absolute" if selector.startswith("/") else "traversal"),
               arguments + [selector], 2, "unrecognized arguments")

    note = next(content.decode() for relative, content in original.items()
                if relative.parent == Path("Voice Inbox"))
    note = note.replace("# " + ACTION["title"], "# Negative fixture")
    thread = next(content.decode() for relative, content in original.items()
                  if relative.parent == Path("Voice Threads"))
    for name, relative, content, reason in (
        ("duplicate YAML", "ordinary.md", "---\ntags: []\ntags: []\n---\n# Ordinary\n", "duplicate YAML"),
        ("invalid metadata tags", "ordinary.md", "---\ntags: [123]\n---\n# Ordinary\n", "tags must be"),
        ("invalid UTF-8", "ordinary.md", b"\xff", "codec"),
        ("whole-vault heading rule", "ordinary.md", "# Ordinary\n### Skipped\n", "skipped heading"),
        ("invalid inline tag", "ordinary.md", "# Ordinary\n#bad_tag\n", "inline tag"),
        ("inbox missing title", "Voice Inbox/Negative fixture.md",
         note.replace("# Negative fixture", "Not a heading"), "requires a title"),
        ("inbox filename mismatch", "Voice Inbox/Wrong title.md", note, "filename must be the title"),
        ("inbox missing timezone", "Voice Inbox/Negative fixture.md", note.replace("+00:00", ""), "timestamp with timezone"),
        ("inbox thread mismatch", "Voice Inbox/Negative fixture.md", note.replace("thread: ", "wrong: "), "thread link"),
        ("thread filename mismatch", "Voice Threads/wrong.md", thread, "filename must match thread_id"),
    ):
        target = vault / relative
        target.write_bytes(content if isinstance(content, bytes) else content.encode())
        try:
            invoke(name, arguments, 1, relative + ":")
            if reason not in VALIDATOR_CASES[-1]["output"]:
                raise RuntimeError(f"vault validation case {name!r} did not explain {reason!r}")
        finally:
            target.unlink()

    outside = root / "outside"
    outside.mkdir()
    sentinel = outside / "untouched.md"
    sentinel.write_text("# Outside\n### Must not be scanned\n", encoding="utf-8")
    before = sentinel.read_bytes()
    for name, target, destination in (
        ("symlink file", vault / "linked.md", sentinel),
        ("symlink directory", vault / "linked", outside),
    ):
        target.symlink_to(destination, target_is_directory=destination.is_dir())
        try:
            invoke(name, arguments, 1, "skipped symlink")
            if "2 notes checked" not in VALIDATOR_CASES[-1]["output"] or sentinel.read_bytes() != before:
                raise RuntimeError("validator followed or changed an out-of-vault symlink")
        finally:
            target.unlink()
    fifo = vault / "pipe.md"
    os.mkfifo(fifo)
    try:
        invoke("nonregular Markdown", arguments, 1, "non-regular file")
    finally:
        fifo.unlink()
    (vault / "case.md").write_text("# Case\n", encoding="utf-8")
    (vault / "CASE.md").write_text("# Case\n", encoding="utf-8")
    try:
        invoke("case-insensitive collision", arguments, 1, "filename collision")
    finally:
        (vault / "case.md").unlink()
        (vault / "CASE.md").unlink()
    unreadable = vault / "unreadable"
    unreadable.mkdir(mode=0o000)
    try:
        invoke("unreadable subtree", arguments, 1, "Permission denied")
    finally:
        unreadable.chmod(0o700)
        unreadable.rmdir()
    invoke("valid again with unchanged original notes", arguments, 0, "0 findings")
    if {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*.md")} != original:
        raise RuntimeError("validator changed original note names or bytes")


def check_sync(executable: Path, source_vault: Path, root: Path, env: dict[str, str]) -> dict[str, str]:
    """Disposable local Git acceptance through the installed console command."""
    sync = executable.with_name("voice-note-vault-sync")
    base = root / "git-acceptance"
    base.mkdir()
    git_env = dict(env, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="Controlled acceptance", GIT_AUTHOR_EMAIL="check@example.invalid",
                   GIT_COMMITTER_NAME="Controlled acceptance", GIT_COMMITTER_EMAIL="check@example.invalid")
    generated = {p.relative_to(source_vault): p.read_bytes() for p in source_vault.rglob("*.md")}

    def git(repo: Path, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(repo), *args], env=git_env, cwd=root,
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError(f"disposable Git setup failed: {args}: {result.stderr}")
        return result.stdout.strip()

    def setup(name: str) -> tuple[Path, Path, Path, dict[str, str]]:
        case = base / name
        case.mkdir()
        remote = case / "remote.git"
        repo = case / "checkout"
        repo.mkdir()
        git(case, "init", "--bare", "--initial-branch=main", str(remote))
        git(repo, "init", "--initial-branch=main")
        git(repo, "config", "user.name", "Controlled acceptance")
        git(repo, "config", "user.email", "check@example.invalid")
        vault = repo / "Different Notebook"
        vault.mkdir()
        (repo / "unrelated.txt").write_bytes(b"unchanged unrelated checkout content\n")
        (vault / "ordinary.md").write_text("# Ordinary\n", encoding="utf-8")
        for relative, content in generated.items():
            target = vault / relative
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(content)
        git(repo, "add", ".")
        git(repo, "commit", "-m", "Disposable baseline")
        git(repo, "push", str(remote), "HEAD:main")
        state_dir = case / "state"
        state_dir.mkdir(mode=0o700)
        selected = dict(git_env, VOICE_VAULT_SYNC="true", VOICE_VAULT_REPO_DIR=str(repo),
                        VOICE_VAULT_DIR=str(vault), VOICE_VAULT_REMOTE=str(remote),
                        VOICE_STATE_DIR=str(state_dir))
        return repo, vault, remote, selected

    def invoke(name: str, repo: Path, remote: Path, selected: dict[str, str], reason: str | None = None) -> None:
        before = git(remote, "rev-parse", "refs/heads/main")
        result = subprocess.run([str(sync)], cwd=root, env=selected, capture_output=True,
                                text=True, timeout=25)
        output = (result.stdout + result.stderr).replace(str(root), "<disposable>")
        after = git(remote, "rev-parse", "refs/heads/main")
        SYNC_CASES.append({"case": name, "returncode": result.returncode, "output": output,
                           "remote_before": before, "remote_after": after,
                           "local_head": git(repo, "rev-parse", "HEAD")})
        if reason is None:
            if result.returncode or after != git(repo, "rev-parse", "HEAD"):
                raise RuntimeError(f"sync {name}: expected success and exact remote HEAD: {output}")
        elif result.returncode == 0 or reason not in output or before != after:
            raise RuntimeError(f"sync {name}: expected refusal {reason!r} and no push: {output}")
        mark("installed Git publication: " + name)

    repo, vault, remote, selected = setup("success")
    original_unrelated = (repo / "unrelated.txt").read_bytes()
    ordinary = (vault / "ordinary.md").read_bytes()
    relative = next(p for p in generated if p.parent == Path("Voice Inbox"))
    (vault / relative).write_bytes(generated[relative] + b"\nPermitted generated update.\n")
    # A preexisting stash must survive our own successful temporary stash cleanup.
    (repo / "unrelated.txt").write_bytes(b"preexisting user stash\n")
    git(repo, "stash", "push", "-m", "user stash")
    user_stash = git(repo, "rev-parse", "refs/stash")
    (vault / relative).write_bytes(generated[relative] + b"\nPermitted generated update.\n")
    invoke("different-name vault restricted publication and remote read-back", repo, remote, selected)
    changed = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
    if (changed != [str(Path(vault.name) / relative)]
            or git(remote, "show", "main:" + str(Path(vault.name) / relative)).encode() + b"\n" != (vault / relative).read_bytes()
            or (repo / "unrelated.txt").read_bytes() != original_unrelated
            or (vault / "ordinary.md").read_bytes() != ordinary
            or git(repo, "rev-parse", "refs/stash") != user_stash):
        raise RuntimeError("publication changed unrelated bytes, staged scope, remote content, or user stash")
    invoke("no-work retry verifies exact remote head", repo, remote, selected)
    disabled = dict(selected, VOICE_VAULT_SYNC="false", VOICE_VAULT_REMOTE=str(base / "missing.git"))
    invoke("default opt-out does not contact even nonexistent selected remote", repo, remote, disabled)

    for name, target, staged in (("unrelated unstaged", repo / "unrelated.txt", False),
                                 ("unrelated staged", vault / "ordinary.md", True),
                                 ("unrelated untracked", vault / "extra.txt", False),
                                 ("nested output", vault / "Voice Inbox/nested/extra.md", False)):
        target.parent.mkdir(exist_ok=True)
        existed = target.exists()
        before_bytes = target.read_bytes() if existed else None
        target.write_bytes(b"# Unrelated modified fixture\n")
        if staged:
            git(repo, "add", str(target.relative_to(repo)))
        index = git(repo, "diff", "--cached", "--binary")
        invoke(name, repo, remote, selected, "outside generated voice paths")
        if target.read_bytes() != b"# Unrelated modified fixture\n" or git(repo, "diff", "--cached", "--binary") != index:
            raise RuntimeError("unrelated refusal changed dirty bytes or staged index")
        if staged:
            git(repo, "restore", "--staged", str(target.relative_to(repo)))
        if existed:
            target.write_bytes(before_bytes)
        else:
            target.unlink()
    pending = vault / relative
    saved = pending.read_bytes()
    pending.unlink()
    try:
        invoke("generated deletion refused", repo, remote, selected, "deletion is refused")
    finally:
        pending.write_bytes(saved)
    unrelated_voice = vault / "Voice Threads" / (str(uuid.uuid4()) + ".md")
    unrelated_voice.write_text(
        '---\nthread_id: "' + unrelated_voice.stem + '"\n---\n# Voice Thread\n', encoding="utf-8")
    # Valid lint metadata but not the writer's exact leading identity header.
    unrelated_voice.write_text(unrelated_voice.read_text().replace("---\nthread_id", "---\ntags: []\nthread_id"))
    try:
        invoke("unrelated valid voice note identity refused", repo, remote, selected, "generated identity")
    finally:
        unrelated_voice.unlink()
    git(repo, "mv", "unrelated.txt", "Different Notebook/Voice Inbox/renamed.md")
    invoke("rename source and destination scopes", repo, remote, selected, "outside generated voice paths")
    git(repo, "reset", "--hard", "HEAD")  # disposable fixture only, never recovery logic

    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "BISECT_LOG", "index.lock", "rebase-merge", "rebase-apply", "sequencer"):
        target = repo / ".git" / marker
        if marker in {"rebase-merge", "rebase-apply", "sequencer"}:
            target.mkdir()
        else:
            target.write_text(git(repo, "rev-parse", "HEAD") + "\n", encoding="utf-8")
        try:
            invoke("active Git operation " + marker, repo, remote, selected, "Git operation already in progress")
        finally:
            target.rmdir() if target.is_dir() else target.unlink()

    for name, changed_env in (
        ("relative repository", {"VOICE_VAULT_REPO_DIR": "checkout"}),
        ("nonexistent repository", {"VOICE_VAULT_REPO_DIR": str(base / "missing")}),
        ("filesystem root repository", {"VOICE_VAULT_REPO_DIR": "/"}),
        ("relative vault", {"VOICE_VAULT_DIR": "Different Notebook"}),
        ("filesystem root vault", {"VOICE_VAULT_DIR": "/"}),
        ("traversal vault", {"VOICE_VAULT_DIR": str(vault / ".." / vault.name)}),
        ("invalid branch boundary", {"VOICE_VAULT_BRANCH": "../main"}),
        ("unselected SSH key", {"VOICE_VAULT_GIT_SSH_KEY": str(base / "missing-key")}),
        ("noncanonical local remote", {"VOICE_VAULT_REMOTE": str(remote / ".." / remote.name)}),
        ("traversal repository", {"VOICE_VAULT_REPO_DIR": str(repo / ".." / repo.name)}),
        ("vault outside repository", {"VOICE_VAULT_DIR": str(source_vault)}),
        ("Git metadata vault", {"VOICE_VAULT_DIR": str(repo / ".git")}),
        ("remote helper refusal", {"VOICE_VAULT_REMOTE": "ext::unsafe"}),
    ):
        invoke(name, repo, remote, dict(selected, **changed_env), "boundary")
    invoke("missing explicit remote", repo, remote, dict(selected, VOICE_VAULT_REMOTE=""), "VOICE_VAULT_REMOTE")
    invoke("wrong selected branch", repo, remote, dict(selected, VOICE_VAULT_BRANCH="other"), "selected branch")
    link = base / "linked-repository"
    link.symlink_to(repo, target_is_directory=True)
    invoke("symlink repository", repo, remote, dict(selected, VOICE_VAULT_REPO_DIR=str(link)), "boundary")
    vault_link = base / "linked-vault"
    vault_link.symlink_to(vault, target_is_directory=True)
    invoke("symlink vault", repo, remote, dict(selected, VOICE_VAULT_DIR=str(vault_link)), "boundary")
    git(vault, "init")
    invoke("nested Git vault", repo, remote, selected, "boundary")
    import shutil
    shutil.rmtree(vault / ".git")  # owned disposable nested metadata only
    (repo / "src/voice_note_intake").mkdir(parents=True)
    invoke("source checkout refused", repo, remote, selected, "source checkout")
    (repo / "src/voice_note_intake").rmdir()
    (repo / "src").rmdir()
    metadata = repo / ".git"
    saved_metadata = repo.parent / "saved-metadata"
    metadata.rename(saved_metadata)
    metadata.symlink_to(saved_metadata, target_is_directory=True)
    try:
        invoke("symlink Git metadata", repo, remote, selected, "boundary")
    finally:
        metadata.unlink()
        saved_metadata.rename(metadata)
    metadata.rename(saved_metadata)
    metadata.write_text("gitdir: " + str(saved_metadata) + "\n", encoding="utf-8")
    try:
        invoke("worktree Git indirection refused", repo, remote, selected, "boundary")
    finally:
        metadata.unlink()
        saved_metadata.rename(metadata)
    git(repo, "checkout", "--detach")
    invoke("detached head", repo, remote, selected, "selected branch")
    git(repo, "checkout", "main")
    (vault / "ordinary.md").write_bytes(b"# Ordinary\n### Invalid whole-vault heading\n")
    # Commit the unrelated invalid baseline so the failure proves whole-vault lint, not status scope.
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Invalid disposable baseline")
    git(repo, "push", str(remote), "HEAD:main")
    invoke("invalid unrelated whole-vault note", repo, remote, selected, "vault lint failed")
    (vault / "ordinary.md").write_bytes(ordinary)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Restore disposable valid baseline")
    git(repo, "push", str(remote), "HEAD:main")
    (vault / relative).write_bytes(generated[relative].replace(b"+00:00", b""))
    invoke("invalid generated note", repo, remote, selected, "vault lint failed")
    git(repo, "restore", str(Path(vault.name) / relative))

    for name in ("remote-unrelated", "remote-reverted-unrelated", "local-ahead-unrelated", "divergence", "restore-conflict", "allowed-fast-forward", "remote-invalid", "remote-source", "missing-remote-branch", "push-failure", "read-back-failure"):
        r, v, rem, sel = setup(name)
        pending = v / relative
        original = pending.read_bytes()
        peer = r.parent / "peer"
        git(r.parent, "clone", str(rem), str(peer))
        if name == "missing-remote-branch":
            git(r, "checkout", "-b", "other")
            invoke(name, r, rem, dict(sel, VOICE_VAULT_BRANCH="other"), "fetch")
            continue
        if name == "local-ahead-unrelated":
            (r / "unrelated.txt").write_text("Local unrelated commit\n", encoding="utf-8")
            git(r, "add", ".")
            git(r, "commit", "-m", "Unrelated outgoing commit")
            invoke(name, r, rem, sel, "outside generated voice paths")
            continue
        if name == "divergence":
            pending.write_bytes(original + b"\nLocal allowed commit\n")
            git(r, "add", ".")
            git(r, "commit", "-m", "Local divergence")
        if name not in {"divergence", "push-failure", "read-back-failure"}:
            pending.write_bytes(original + b"\nLocal pending generated note\n")
        if name.startswith("remote-unrelated") or name == "remote-reverted-unrelated":
            peer_target = peer / "unrelated.txt"
        else:
            peer_target = peer / v.name / relative
        if name not in {"push-failure", "read-back-failure"}:
            peer_target.write_bytes(peer_target.read_bytes() + b"\nRemote concurrent update\n")
            if name == "remote-invalid":
                peer_target.write_bytes(peer_target.read_bytes() + b"\n### Invalid\n")
            if name == "remote-source":
                (peer / "src/voice_note_intake").mkdir(parents=True)
                (peer / "src/voice_note_intake/main.py").write_text("# Source sentinel\n", encoding="utf-8")
            git(peer, "add", ".")
            git(peer, "commit", "-m", "Remote update")
            if name == "remote-reverted-unrelated":
                git(peer, "revert", "--no-edit", "HEAD")
            git(peer, "push", str(rem), "HEAD:main")
        if name == "allowed-fast-forward":
            # No dirty local conflict: prove permitted remote fast-forward and exact readback.
            pending.write_bytes(original)
            invoke(name, r, rem, sel)
            if pending.read_bytes() != peer_target.read_bytes():
                raise RuntimeError("permitted remote update was not read back locally")
            continue
        if name == "remote-invalid":
            pending.write_bytes(original)
            invoke(name, r, rem, sel, "vault lint failed")
            continue
        if name == "read-back-failure":
            pending.write_bytes(original + b"\nPending generated note\n")
            old_head = git(rem, "rev-parse", "refs/heads/main")
            hook = rem / "hooks/post-receive"
            hook.write_text("#!/bin/sh\ngit update-ref refs/heads/main " + old_head + "\n", encoding="utf-8")
            hook.chmod(0o700)
        if name == "push-failure":
            pending.write_bytes(original + b"\nPending generated note\n")
            hook = rem / "hooks/pre-receive"
            hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            hook.chmod(0o700)
        reason = ("diverged" if name == "divergence" else "restoring generated voice changes conflicted"
                  if name == "restore-conflict" else "source checkout" if name == "remote-source"
                  else "remote head does not match" if name == "read-back-failure"
                  else "push" if name == "push-failure" else "outside generated voice paths")
        invoke(name, r, rem, sel, reason)
        if name in {"remote-unrelated", "remote-reverted-unrelated", "restore-conflict", "remote-source", "push-failure", "read-back-failure"}:
            recovery = Path(sel["VOICE_STATE_DIR"]) / "vault-sync-recovery.json"
            data = json.loads(recovery.read_text())
            stash = git(r, "rev-parse", "refs/stash")
            if data["stash"] != stash or not git(r, "show", stash + ":" + str(Path(v.name) / relative)):
                raise RuntimeError("sync failure did not preserve recoverable stash and JSON evidence")
            if name in {"remote-unrelated", "remote-reverted-unrelated"} and pending.read_bytes() != original + b"\nLocal pending generated note\n":
                raise RuntimeError("refusal failed to restore local pending bytes")
            SYNC_CASES[-1]["preserved_stash"] = stash
            SYNC_CASES[-1]["recovery"] = data
            invoke(name + " recovery blocks retries", r, rem, sel, "recovery")

    r, v, rem, sel = setup("repository-root-vault")
    for child in list(v.iterdir()):
        child.rename(r / child.name)
    v.rmdir()
    git(r, "add", ".")
    git(r, "commit", "-m", "Disposable root-vault baseline")
    git(r, "push", str(rem), "HEAD:main")
    pending = r / relative
    pending.write_bytes(pending.read_bytes() + b"\nAllowed committed generated update\n")
    git(r, "add", str(relative))
    git(r, "commit", "-m", "Allowed generated local commit")
    invoke("repository-root vault publishes allowed local-ahead commit", r, rem,
           dict(sel, VOICE_VAULT_DIR=str(r)))

    # Return a clean dedicated selected checkout for the existing HTTP worker acceptance.
    _, _, _, selected = setup("http-worker")
    return selected


def check(executable: Path, root: Path) -> None:
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError("installed voice-note-intake executable is missing or not executable")
    home = root / "home"
    state_dir = root / "state"
    archive_dir = root / "archive"
    vault_dir = root / "Notebook Trial"
    for directory in (home, state_dir, archive_dir, vault_dir):
        directory.mkdir(parents=True)
    # Exercise the documented correction for an existing operator-owned state directory.
    state_dir.chmod(0o755)
    subprocess.run(["mkdir", "-p", "-m", "700", str(state_dir)], check=True)
    subprocess.run(["chmod", "700", str(state_dir)], check=True)
    mark("documented mkdir/chmod setup repairs existing private state under ordinary umask")
    path = str(Path(sys.executable).resolve().parent) + os.pathsep + os.defpath
    env = clean_env(home, path)

    try:
        subprocess.run([str(executable), "--help"], env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("installed console entry point --help failed") from error
    mark("installed console entry point runs outside the source tree")

    port = allocate_port()
    missing_env = dict(env)
    missing_env.update({
        "VOICE_ARCHIVE_DIR": str(archive_dir),
        "VOICE_VAULT_DIR": str(vault_dir),
        "VOICE_REQUIRE_NFS_MOUNT": "false",
    })
    try:
        missing = subprocess.run(
            [str(executable), "--host", "127.0.0.1", "--port", str(port)], env=missing_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("service started instead of rejecting missing endpoint/model configuration") from error
    combined = missing.stdout + missing.stderr
    if missing.returncode == 0 or "VOICE_ASR_URL" not in combined:
        raise RuntimeError("missing configuration was not rejected with the required VOICE_ASR_URL")
    mark("missing endpoint/model settings fail before service startup")

    state = FixtureState()
    fixture = FixtureServer(state)
    env.update({
        "VOICE_STATE_DIR": str(state_dir),
        "VOICE_ARCHIVE_DIR": str(archive_dir),
        "VOICE_VAULT_DIR": str(vault_dir),
        "VOICE_REQUIRE_NFS_MOUNT": "false",
        "VOICE_ASR_URL": fixture.base_url + "/asr",
        "VOICE_LLM_URL": fixture.base_url + "/llm",
        "VOICE_LLM_MODEL": "controlled-model",
        "VOICE_NTFY_URL": fixture.base_url + "/notify",
        "VOICE_HTTP_TIMEOUT": "5",
        "VOICE_LLM_PRIMARY_TIMEOUT": "5",
        "VOICE_MAX_RETRIES": "2",
    })
    default_probe = subprocess.run(
        [sys.executable, "-c",
         "from voice_note_intake.config import Config; c=Config.from_env(); "
         "print(c.bind_host, c.require_nfs_mount)"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
    )
    if default_probe.returncode or default_probe.stdout.strip() != "127.0.0.1 False":
        fixture.close()
        raise RuntimeError("portable defaults must be loopback binding and local archive mode")
    mark("portable defaults are loopback-only with intentional local archive mode")

    sync_env = dict(env)
    sync_env["VOICE_VAULT_SYNC"] = "true"
    sync_probe = subprocess.run(
        [sys.executable, "-c", "from voice_note_intake.config import Config; Config.from_env()"],
        env=sync_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
    )
    if sync_probe.returncode == 0 or "VOICE_VAULT_REPO_DIR" not in sync_probe.stderr:
        fixture.close()
        raise RuntimeError("opt-in publication without explicit repository boundary was not refused with VOICE_VAULT_REPO_DIR: " + sync_probe.stderr)
    mark("opt-in publication requires explicit repository boundary")

    service_port = allocate_port()
    log_path = root / "service.log"
    log = log_path.open("wb")
    service = subprocess.Popen(
        [str(executable), "--port", str(service_port)], cwd=root, env=env,
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        base = f"http://127.0.0.1:{service_port}"
        deadline = time.monotonic() + 15
        health: Any = None
        while time.monotonic() < deadline:
            if service.poll() is not None:
                raise RuntimeError("installed service exited before readiness; inspect private service.log")
            try:
                status, health = request_json(base + "/health", timeout=1)
                if status == 200 and isinstance(health, dict) and health.get("ready") is True:
                    break
            except (OSError, TimeoutError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("installed service did not become ready; inspect private service.log")
        mark("HTTP readiness reports ready")

        audio = make_audio()
        request_id = str(uuid.uuid4())
        boundary, payload = multipart(audio, request_id)
        status, received = request_json(
            base + "/v1/voice-notes", method="POST", body=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=10,
        )
        if status != 202 or not isinstance(received, dict) or received.get("status") != "received":
            raise RuntimeError("multipart upload did not return durable-intake HTTP 202")
        expected_hash = hashlib.sha256(audio).hexdigest()
        if received.get("request_id") != request_id or received.get("sha256") != expected_hash:
            raise RuntimeError("accepted job metadata does not match the controlled upload")
        mark("multipart audio upload returns HTTP 202 after durable acceptance")
        if Path(received["spool_path"]).read_bytes() != audio or not state.asr_entered.wait(timeout=5):
            raise RuntimeError("acknowledged audio is not durable or controlled ASR did not start")
        status, processing = request_json(base + "/v1/jobs/" + request_id)
        if status != 200 or processing["status"] != "archived":
            raise RuntimeError("controlled ASR gate did not hold the job during processing")
        other_audio = audio[:-2] + b"\x01\x00"
        for retry_audio in (audio, other_audio):
            boundary, payload = multipart(retry_audio, request_id)
            status, duplicate = request_json(
                base + "/v1/voice-notes", method="POST", body=payload,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            if (status != 202 or duplicate.get("idempotent") is not True
                    or duplicate["status"] != "archived" or duplicate["sha256"] != expected_hash
                    or duplicate["thread_id"] != request_id or duplicate["byte_count"] != len(audio)
                    or Path(duplicate["spool_path"]).read_bytes() != audio
                    or Path(duplicate["archive_path"]).read_bytes() != audio):
                raise RuntimeError("processing retry replaced audio or did not return the existing job")
        mark("same and different audio retries during processing retain the existing job and bytes")
        service.kill()  # owned child only: abrupt interruption, not graceful cancellation
        service.wait(timeout=5)
        state.asr_release.set()
        service = subprocess.Popen(
            [str(executable), "--port", str(service_port)], cwd=root, env=env,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                status, health = request_json(base + "/health", timeout=1)
                if status == 200 and health.get("ready") is True:
                    break
            except (OSError, TimeoutError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("restarted installed process did not become ready")
        mark("owned process is interrupted after HTTP 202 and restarted with the same state")

        deadline = time.monotonic() + 25
        job: Any = None
        while time.monotonic() < deadline:
            status, job = request_json(base + "/v1/jobs/" + request_id)
            if status == 200 and isinstance(job, dict) and job.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.1)
        if not isinstance(job, dict) or job.get("status") != "completed":
            raise RuntimeError("job did not reach durable completed status")
        mark("durable job status reaches completed")

        archived = Path(job.get("archive_path", ""))
        if archived.parent != archive_dir or archived.read_bytes() != audio:
            raise RuntimeError("archived audio differs from the submitted WAV fixture")
        if hashlib.sha256(archived.read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError("archived audio SHA-256 does not match the upload")
        transcript_path = Path(job.get("transcript_path", ""))
        if (transcript_path.parent != state_dir / "transcripts"
                or transcript_path.read_text(encoding="utf-8") != TRANSCRIPT):
            raise RuntimeError("controlled transcript was not durably saved as expected")
        mark("archive bytes and SHA-256 match the uploaded WAV fixture")
        mark("controlled ASR transcript is persisted and passed to the formatter")

        note = vault_dir / job["note_path"]
        note_text = note.read_text(encoding="utf-8")
        if (ACTION["title"] not in note_text or ACTION["body"] not in note_text
                or f'request_id: "{request_id}"' not in note_text
                or f'thread_id: "{request_id}"' not in note_text
                or f'source_sha256: "{expected_hash}"' not in note_text):
            raise RuntimeError("generated note content or request/thread metadata is incomplete")
        thread = vault_dir / "Voice Threads" / f"{request_id}.md"
        thread_text = thread.read_text(encoding="utf-8")
        if ("Controlled library reminder" not in thread_text or ACTION["summary"] not in thread_text
                or f'thread_id: "{request_id}"' not in thread_text
                or "[[Voice Inbox/Controlled library reminder]]" not in thread_text):
            raise RuntimeError("generated thread index is missing expected metadata or linked note summary")
        if not state.transcript_seen:
            raise RuntimeError("controlled LLM did not receive the controlled ASR transcript")
        mark("generated note and thread index contain expected content")
        check_vault(executable, vault_dir, root)

        status, history = request_json(fixture.base_url + "/notify/json")
        event_id = job.get("notification_event_id")
        event = state.notification
        if (status != 200 or not isinstance(history, dict)
                or not isinstance(event, dict) or event_id != event.get("id")
                or history.get("id") != event_id
                or history.get("title") != "Voice note completed"
                or job["note_path"] not in history.get("message", "")
                or f"Request: {request_id}" not in history.get("message", "")
                or f"Thread: {request_id}" not in history.get("message", "")):
            raise RuntimeError("completion notification ID/content did not read back from controlled history")
        if state.audio != audio:
            raise RuntimeError("controlled ASR upstream did not receive the exact archived audio")
        mark("controlled notification event is captured and read back by exact ID")
        for retry_audio in (audio, other_audio):
            boundary, payload = multipart(retry_audio, request_id)
            status, duplicate = request_json(
                base + "/v1/voice-notes", method="POST", body=payload,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            if (status != 202 or duplicate.get("idempotent") is not True
                    or duplicate["status"] != "completed" or duplicate["sha256"] != expected_hash
                    or duplicate["thread_id"] != request_id or duplicate["byte_count"] != len(audio)
                    or duplicate["note_path"] != job["note_path"]
                    or Path(duplicate["spool_path"]).read_bytes() != audio
                    or archived.read_bytes() != audio or note.read_text() != note_text
                    or thread.read_text() != thread_text):
                raise RuntimeError("completed retry replaced accepted audio or generated outputs")
        notes = [p for p in (vault_dir / "Voice Inbox").glob("*.md")
                 if f'request_id: "{request_id}"' in p.read_text()]
        status, threads = request_json(base + "/v1/threads")
        members = [t for t in threads["threads"] if t["thread_id"] == request_id]
        if (len(notes) != 1 or thread_text.count(f"<!-- {request_id} -->") != 1
                or status != 200 or len(members) != 1 or members[0]["recording_count"] != 1
                or members[0]["latest_status"] != "completed"):
            raise RuntimeError("restart or duplicate uploads created multiple jobs/notes/thread entries")
        mark("same and different audio retries after completion preserve one note and one thread entry")

        def restart() -> None:
            nonlocal service
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=5)
            service = subprocess.Popen(
                [str(executable), "--port", str(service_port)], cwd=root, env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if service.poll() is not None:
                    raise RuntimeError("scenario restart exited before readiness")
                try:
                    status, health = request_json(base + "/health", timeout=1)
                    if status == 200 and health.get("ready") is True:
                        return
                except (OSError, TimeoutError, urllib.error.URLError):
                    pass
                time.sleep(0.1)
            raise RuntimeError("scenario restart failed readiness")

        # Same installed HTTP worker, now explicitly opted into a disposable selected checkout.
        selected = check_sync(executable, vault_dir, root, env)
        original_env = dict(env)
        env.update(selected)
        restart()
        published = submit(base, audio)
        published = wait_job(base, published["request_id"], lambda j: j["status"] == "completed",
                             "opt-in HTTP worker publishes before completion notification")
        publish_repo = Path(selected["VOICE_VAULT_REPO_DIR"])
        publish_vault = Path(selected["VOICE_VAULT_DIR"])
        publish_remote = Path(selected["VOICE_VAULT_REMOTE"])

        def read_git(repo: Path, *arguments: str) -> str:
            return subprocess.run(["git", "-C", str(repo), *arguments], env=selected,
                                  capture_output=True, text=True, check=True, timeout=5).stdout.strip()

        head = read_git(publish_repo, "rev-parse", "HEAD")
        if head != read_git(publish_remote, "rev-parse", "refs/heads/main"):
            raise RuntimeError("HTTP completion happened without exact bare remote commit")
        remote_note = read_git(publish_remote, "show", "main:" + str(Path(publish_vault.name) / published["note_path"]))
        if remote_note != (publish_vault / published["note_path"]).read_text().strip():
            raise RuntimeError("HTTP completion remote note read-back differs from local generated note")
        event = next(e for e in state.events if e["id"] == published["notification_event_id"])
        if event["title"] != "Voice note completed" or published["note_path"] not in event["message"]:
            raise RuntimeError("published HTTP note did not have exact completion notification read-back")
        SYNC_CASES.append({"case": "HTTP worker opt-in completed publication", "remote_head": head,
                           "note_path": published["note_path"], "notification_event_id": event["id"]})
        mark("opt-in HTTP worker publishes generated note/thread and verifies remote before completion notification")
        protected = publish_repo / "unrelated.txt"
        protected.write_bytes(b"Protected dirty unrelated bytes\n")
        refused_sync = submit(base, audio)
        refused_sync = wait_job(base, refused_sync["request_id"],
                                lambda j: j["status"] == "failed" and j["notification_event_id"] is not None,
                                "HTTP worker sync refusal persists lint_or_sync", timeout=20)
        event = next(e for e in state.events if e["id"] == refused_sync["notification_event_id"])
        if (refused_sync["error_stage"] != "lint_or_sync" or refused_sync["retry_count"] != 2
                or refused_sync["note_path"] is None or event["title"] != "Voice note failed"
                or protected.read_bytes() != b"Protected dirty unrelated bytes\n"
                or read_git(publish_remote, "rev-parse", "refs/heads/main") != head
                or any(e["title"] == "Voice note completed" and refused_sync["request_id"] in e["message"] for e in state.events)):
            raise RuntimeError("HTTP sync refusal overwrote dirty bytes, pushed, or notified completion")
        restart()
        persisted = wait_job(base, refused_sync["request_id"], lambda j: j["status"] == "failed",
                             "HTTP sync refusal survives restart")
        if persisted["error_stage"] != "lint_or_sync":
            raise RuntimeError("HTTP sync failure stage was not durable")
        mark("HTTP sync refusal preserves generated note and unrelated bytes; no push/completion; durable lint_or_sync")
        env.clear()
        env.update(original_env)
        restart()

        def originals(job: dict[str, Any]) -> None:
            if (job["sha256"] != expected_hash or Path(job["spool_path"]).read_bytes() != audio
                    or Path(job["archive_path"]).read_bytes() != audio):
                raise RuntimeError("failure scenario lost or replaced accepted original audio")

        def notes_for(request: str) -> list[Path]:
            return [p for p in (vault_dir / "Voice Inbox").glob("*.md")
                    if f'request_id: "{request}"' in p.read_text()]

        # Failure scenarios were recorded before any application correction.
        state.asr_fail = True
        transient = submit(base, audio)
        retry = wait_job(base, transient["request_id"], lambda j: j["retry_count"] == 1,
                         "ASR HTTP 503 persists first retry")
        if retry["status"] != "archived" or retry["error_stage"] != "transcribe":
            raise RuntimeError("ASR outage did not preserve retryable transcription state")
        originals(retry)
        state.asr_fail = False
        wait_job(base, transient["request_id"], lambda j: j["status"] == "completed",
                 "ASR restores and completes without resubmission")
        mark("controlled transient ASR outage persists retry state and recovers")

        failed_jobs = []
        invalid_outputs = [
            json.dumps({**ACTION, "operation": "overwrite", "path": "../protected.md"}),
            json.dumps({**ACTION, "body": ""}),
            json.dumps({**ACTION, "tags": "not-an-array"}),
        ]
        scenarios = [("unavailable ASR HTTP 503", "transcribe", None),
                     ("unavailable LLM HTTP 503", "format", None)]
        scenarios += [(f"invalid structured output {i + 1}", "format", content)
                      for i, content in enumerate(invalid_outputs)]
        for name, stage, content in scenarios:
            state.asr_fail = stage == "transcribe"
            state.llm_fail = name == "unavailable LLM HTTP 503"
            state.action_content = content if content is not None else json.dumps(ACTION)
            calls_before = dict(state.calls)
            accepted = submit(base, audio)
            failed = wait_job(base, accepted["request_id"],
                              lambda j: j["status"] == "failed" and j["notification_event_id"], name)
            if (failed["retry_count"] != 2 or failed["error_stage"] != stage
                    or failed["note_path"] is not None or notes_for(failed["request_id"])):
                raise RuntimeError(name + ": retry limit or no-invalid-note contract failed")
            originals(failed)
            expected_calls = 2 if content is None else 4  # one repair per formatting attempt
            key = "asr" if stage == "transcribe" else "llm"
            if state.calls[key] - calls_before[key] != expected_calls:
                raise RuntimeError(name + ": unexpected bounded inference/repair count")
            failed_jobs.append(failed)
        state.asr_fail = state.llm_fail = False
        state.action_content = json.dumps(ACTION)
        mark("unavailable ASR/LLM and three invalid structured outputs fail durably without notes")
        restart()
        for failed in failed_jobs:
            persisted = wait_job(base, failed["request_id"], lambda j: j["status"] == "failed",
                                 "failed inference state survives installed-process restart")
            if any(persisted[k] != failed[k] for k in (
                "sha256", "retry_count", "error_stage", "notification_event_id")):
                raise RuntimeError("restart changed terminal failure/retry metadata")
            originals(persisted)
        mark("failed inference statuses, retry counts and original bytes survive restart")

        state.notify_failures = 1
        accepted = submit(base, audio)
        retry = wait_job(base, accepted["request_id"], lambda j: j["retry_count"] == 1,
                         "notification HTTP 503 preserves writing status")
        if (retry["status"] != "writing" or retry["error_stage"] != "write_or_notify"
                or retry["notification_event_id"] is not None or len(notes_for(retry["request_id"])) != 1):
            raise RuntimeError("notification outage lost durable writing/retry state")
        written = (vault_dir / retry["note_path"]).read_bytes()
        completed = wait_job(base, accepted["request_id"], lambda j: j["status"] == "completed",
                             "notification retry completes")
        if (len(notes_for(completed["request_id"])) != 1
                or (vault_dir / completed["note_path"]).read_bytes() != written):
            raise RuntimeError("notification retry duplicated or replaced the valid note")
        mark("notification outage retries from durable writing state without duplicating notes")

        state.notify_accept_then_fail = True
        notify_before = state.calls["notify"]
        accepted = submit(base, audio)
        completed = wait_job(base, accepted["request_id"], lambda j: j["status"] == "completed",
                             "accepted notification with ambiguous HTTP 503 recovers from history")
        with urllib.request.urlopen(fixture.base_url + "/notify/json", timeout=5) as response:
            events = [json.loads(line) for line in response.read().splitlines()]
        matches = [e for e in events if f"Request: {accepted['request_id']}" in e["message"]]
        if (completed["retry_count"] != 1 or state.calls["notify"] - notify_before != 1
                or len(matches) != 1 or matches[0]["id"] != completed["notification_event_id"]):
            raise RuntimeError("ambiguous notification was not read back by exact ID before republishing")
        mark("controlled delivered-but-503 notification recovers cached exact event without another POST")

        protected = vault_dir / "Voice Inbox" / "Controlled library reminder.md"
        protected_bytes = protected.read_bytes()  # existing note belongs to first unrelated request
        accepted = submit(base, audio)
        completed = wait_job(base, accepted["request_id"], lambda j: j["status"] == "completed",
                             "title collision uses create-only output")
        if (protected.read_bytes() != protected_bytes
                or completed["note_path"] == protected.relative_to(vault_dir).as_posix()):
            raise RuntimeError("create-only writer overwrote an unrelated existing note")
        mark("unrelated same-title note remains byte-identical; collision gets a new create-only path")

        conflict_id = str(uuid.uuid4())
        protected_thread = vault_dir / "Voice Threads" / f"{conflict_id}.md"
        protected_thread.write_bytes(b"Unrelated protected thread content\n")
        submit(base, audio, conflict_id)
        conflict = wait_job(base, conflict_id, lambda j: j["status"] == "failed", "unrelated thread output refusal")
        if (conflict["error_stage"] != "write_or_notify"
                or protected_thread.read_bytes() != b"Unrelated protected thread content\n"):
            raise RuntimeError("existing unrelated thread output was overwritten")
        mark("unrelated thread output is refused and its protected content is unchanged")

        unsafe_env = dict(env)
        unsafe_env["VOICE_INBOX"] = "../protected"
        refused = subprocess.run([str(executable), "--port", str(allocate_port())],
                                 cwd=root, env=unsafe_env, capture_output=True, timeout=5)
        if refused.returncode == 0 or b"VOICE_INBOX" not in refused.stderr:
            raise RuntimeError("unsafe configured output path was not rejected at startup")
        state.asr_entered.clear()
        state.asr_release.clear()
        accepted = submit(base, audio)
        if not state.asr_entered.wait(timeout=5):
            raise RuntimeError("unsafe-output scenario could not gate accepted job")
        inbox = vault_dir / "Voice Inbox"
        saved_inbox = vault_dir / "Saved Inbox"
        outside = root / "protected-output"
        outside.mkdir()
        outside_note = outside / "Controlled library reminder.md"
        outside_note.write_bytes(b"Protected outside vault\n")
        inbox.rename(saved_inbox)
        inbox.symlink_to(outside, target_is_directory=True)
        try:
            status, health = request_json(base + "/health")
            if status != 503 or health["paths"]["inbox"]["usable"]:
                raise RuntimeError("unsafe symlink output path did not fail readiness")
            state.asr_release.set()
            failed = wait_job(base, accepted["request_id"], lambda j: j["status"] == "failed",
                              "unsafe symlink output path refuses writing")
            if (failed["error_stage"] != "write_or_notify" or failed["note_path"] is not None
                    or outside_note.read_bytes() != b"Protected outside vault\n"
                    or sorted(p.name for p in outside.iterdir()) != [outside_note.name]):
                raise RuntimeError("unsafe output path wrote or changed protected outside content")
            originals(failed)
        finally:
            inbox.unlink()
            saved_inbox.rename(inbox)
            state.asr_release.set()
        mark("unsafe configured and symlinked output paths refuse writes with protected bytes unchanged")

        # Retention: real HTTP-created completed/failed jobs, gated active and received jobs,
        # and an unresolved recording not associated with a completed job.
        preserved = {p: p.read_bytes() for parent in (state_dir / "spool", state_dir / "transcripts", vault_dir)
                     for p in parent.rglob("*") if p.is_file() and not p.name.endswith(".lock")}
        unresolved = archive_dir / "unresolved-recording.audio"
        unresolved.write_bytes(other_audio)
        state.asr_entered.clear()
        state.asr_release.clear()
        active = submit(base, audio)
        if not state.asr_entered.wait(timeout=5):
            raise RuntimeError("retention could not gate active archived job")
        active = wait_job(base, active["request_id"], lambda j: j["status"] == "archived", "active archive before retention")
        queued = submit(base, audio)
        env["VOICE_ARCHIVE_MAX_BYTES"] = "0"
        restart()
        for old_request in (request_id, transient["request_id"], completed["request_id"]):
            deleted = wait_job(base, old_request, lambda j: j["archive_deleted_at"] is not None,
                               "configured zero-cap retention deletes completed original")
            if deleted["status"] != "completed" or deleted["archive_delete_outcome"] != "deleted" or Path(deleted["archive_path"]).exists():
                raise RuntimeError("retention did not remove only completed eligible original")
        originals(active)
        for failed in failed_jobs:
            originals(failed)
        queued_status = wait_job(base, queued["request_id"], lambda j: j["status"] == "received", "queued active original excluded from retention")
        if (Path(queued_status["spool_path"]).read_bytes() != audio
                or unresolved.read_bytes() != other_audio
                or any(path.read_bytes() != content for path, content in preserved.items())):
            raise RuntimeError("retention modified active/unresolved audio or local spool/transcript/note outputs")
        mark("zero-cap retention deletes completed archives only; active/failed/unresolved and local artifacts preserved")
        state.asr_release.set()
        wait_job(base, queued["request_id"], lambda j: j["status"] == "completed", "retention active queue resumes")

        state.notify_failures = 100
        accepted = submit(base, audio)
        writing = wait_job(base, accepted["request_id"], lambda j: j["status"] == "writing" and j["retry_count"] == 1,
                           "unresolved notification job excluded from zero-cap retention")
        originals(writing)
        if len(notes_for(writing["request_id"])) != 1:
            raise RuntimeError("unresolved notification note is missing or duplicated")
        written = (vault_dir / writing["note_path"]).read_bytes()
        failed = wait_job(base, accepted["request_id"], lambda j: j["status"] == "failed", "notification processing retry limit")
        originals(failed)
        restart()
        persisted = wait_job(base, accepted["request_id"], lambda j: j["status"] == "failed", "notification failure survives restart")
        if (persisted["retry_count"] != 2 or persisted["notification_event_id"] is not None
                or (vault_dir / persisted["note_path"]).read_bytes() != written):
            raise RuntimeError("notification failure did not persist bounded processing retries and valid note")
        state.notify_failures = 0
        recovered = wait_job(base, accepted["request_id"], lambda j: j["notification_event_id"] is not None,
                             "terminal failure notification continues retrying until delivery", timeout=20)
        if recovered["status"] != "failed" or recovered["retry_count"] != 2:
            raise RuntimeError("failure notification recovery reset durable processing failure")
        with urllib.request.urlopen(fixture.base_url + "/notify/json", timeout=5) as response:
            events = [json.loads(line) for line in response.read().splitlines()]
        event = next((e for e in events if e["id"] == recovered["notification_event_id"]), None)
        if event is None or event["title"] != "Voice note failed" or f"Request: {accepted['request_id']}" not in event["message"]:
            raise RuntimeError("recovered failure notification did not read back by exact ID")
        mark("unresolved/failed notification archives remain; processing retries bounded and failure delivery resumes")
    finally:
        service.terminate()
        try:
            service.wait(timeout=5)
        except subprocess.TimeoutExpired:
            service.kill()
            service.wait(timeout=5)
        log.close()
        fixture.close()

    nfs_state = root / "nfs-state"
    nfs_state.mkdir(mode=0o700)
    nfs_env = dict(env)
    nfs_env["VOICE_STATE_DIR"] = str(nfs_state)
    nfs_env["VOICE_REQUIRE_NFS_MOUNT"] = "true"
    nfs_port = allocate_port()
    nfs_log = (root / "nfs-service.log").open("wb")
    nfs_service = subprocess.Popen(
        [str(executable), "--port", str(nfs_port)], cwd=root, env=nfs_env,
        stdin=subprocess.DEVNULL, stdout=nfs_log, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if nfs_service.poll() is not None:
                raise RuntimeError("NFS-validation service exited before health check")
            try:
                status, health = request_json(f"http://127.0.0.1:{nfs_port}/health", timeout=1)
                archive = health.get("paths", {}).get("archive", {}) if isinstance(health, dict) else {}
                if (status == 503 and archive.get("nfs_required") is True
                        and archive.get("nfs_mount") is False):
                    break
            except (OSError, TimeoutError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("opt-in NFS policy did not reject the ordinary local archive directory")
        mark("opt-in NFS validation rejects an ordinary local archive directory")
    finally:
        nfs_service.terminate()
        try:
            nfs_service.wait(timeout=5)
        except subprocess.TimeoutExpired:
            nfs_service.kill()
            nfs_service.wait(timeout=5)
        nfs_log.close()


def check_real(executable: Path, root: Path, audio_path: Path, words: list[str], timeout: float) -> dict:
    """Same installed listener/helpers, real inference; only notification is controlled."""
    import shlex
    import sqlite3

    home, state_dir, archive, repo = (root / name for name in ("home", "state", "archive", "checkout"))
    vault, remote = repo / "Acceptance Notebook", root / "remote.git"
    for directory in (home, archive, vault):
        directory.mkdir(parents=True)
    subprocess.run(["mkdir", "-p", "-m", "700", str(state_dir)], check=True)
    subprocess.run(["chmod", "700", str(state_dir)], check=True)
    env = clean_env(home, str(executable.parent) + os.pathsep + os.defpath)
    # Never inherit a production vault/archive/topic, credentials, Git overrides or Python path.
    for name in ("VOICE_ASR_URL", "VOICE_LLM_URL", "VOICE_LLM_MODEL",
                 "VOICE_HTTP_TIMEOUT", "VOICE_LLM_PRIMARY_TIMEOUT"):
        if not os.environ.get(name):
            raise RuntimeError("real acceptance requires explicit " + name)
        env[name] = os.environ[name]
    env.update(VOICE_STATE_DIR=str(state_dir), VOICE_ARCHIVE_DIR=str(archive),
               VOICE_VAULT_DIR=str(vault), VOICE_REQUIRE_NFS_MOUNT="false",
               VOICE_VAULT_SYNC="true", VOICE_VAULT_REPO_DIR=str(repo),
               VOICE_VAULT_REMOTE=str(remote), VOICE_VAULT_BRANCH="main", VOICE_MAX_RETRIES="2")

    def git(target: Path, *args: str) -> bytes:
        return subprocess.run(["git", "-C", str(target), *args], cwd=root, env=env,
                              capture_output=True, check=True, timeout=10).stdout

    git(root, "init", "--bare", "--initial-branch=main", str(remote))
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Disposable acceptance")
    git(repo, "config", "user.email", "acceptance@example.invalid")
    sentinel = vault / "ordinary.md"
    sentinel.write_bytes(b"# Disposable baseline\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Disposable baseline")
    git(repo, "push", str(remote), "HEAD:main")
    baseline = git(remote, "rev-parse", "refs/heads/main").strip()
    state = FixtureState()
    fixture = FixtureServer(state)
    env["VOICE_NTFY_URL"] = fixture.base_url + "/notify"
    publication_at_notify: list[dict] = []

    def before_notify(body: bytes) -> None:
        head = git(repo, "rev-parse", "HEAD").strip()
        if head == baseline or head != git(remote, "rev-parse", "refs/heads/main").strip():
            raise RuntimeError("notification attempted before exact remote HEAD")
        outputs = list(vault.glob("Voice Inbox/*.md")) + list(vault.glob("Voice Threads/*.md"))
        if len(outputs) != 2 or "Completed voice note" not in body.decode():
            raise RuntimeError("notification attempted without real note/thread completion")
        for output in outputs:
            if git(remote, "show", "main:" + output.relative_to(repo).as_posix()) != output.read_bytes():
                raise RuntimeError("notification attempted before exact remote output bytes")
        publication_at_notify.append({"head": head.decode(), "verified_output_count": len(outputs)})

    state.before_notify = before_notify
    env_file = root / "env"
    env_file.write_text("\n".join(f"export {key}={shlex.quote(value)}" for key, value in env.items()) + "\n")
    env_file.chmod(0o600)
    probe = subprocess.run([str(executable.with_name("python")), "-c",
                            "import json, voice_note_intake; "
                            "from importlib.metadata import version; "
                            "print(json.dumps({'module': voice_note_intake.__file__, "
                            "'version': version('voice-note-intake')}))"],
                           cwd=root, env=env, capture_output=True, text=True, check=True, timeout=5)
    installed = json.loads(probe.stdout)
    if "site-packages" not in installed["module"] or installed["version"] != "0.1.0":
        fixture.close()
        raise RuntimeError("real run did not import installed distribution")
    mark("clean installed distribution imports from external environment, no source/Hermes path")
    service_port = allocate_port()
    log = (root / "service.log").open("wb")
    service = subprocess.Popen([str(executable), "--host", "127.0.0.1", "--port", str(service_port)],
                               cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{service_port}"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if service.poll() is not None:
                raise RuntimeError("real installed listener exited; inspect private service.log")
            try:
                status, health = request_json(base + "/health", timeout=1)
                if status == 200 and health.get("ready") is True:
                    break
            except (OSError, TimeoutError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("real installed listener readiness timeout")
        mark("documented private state setup and loopback readiness")
        audio = audio_path.read_bytes()
        with wave.open(io.BytesIO(audio)) as speech:
            if speech.getnframes() == 0:
                raise RuntimeError("real audio must be nonempty known-speech WAV")
        accepted = submit(base, audio)
        digest = hashlib.sha256(audio).hexdigest()
        if accepted["sha256"] != digest or accepted["byte_count"] != len(audio):
            raise RuntimeError("real durable acceptance upload integrity mismatch")
        mark("known-speech WAV accepted durably with HTTP 202")
        job = wait_job(base, accepted["request_id"], lambda j: j["status"] in {"completed", "failed"},
                       "real inference terminal status", timeout=timeout)
        (root / "job.json").write_text(json.dumps(job, indent=2) + "\n")
        if job["status"] != "completed" or job["error_stage"] or job["error_message"] or not job["completed_at"]:
            raise RuntimeError("real inference did not complete; inspect private job.json")
        for path in (job["spool_path"], job["archive_path"]):
            if Path(path).read_bytes() != audio:
                raise RuntimeError("real original audio changed across spool/archive")
        transcript = Path(job["transcript_path"]).read_text()
        note = (vault / job["note_path"]).read_bytes()
        thread = (vault / "Voice Threads" / f"{job['thread_id']}.md").read_bytes()
        # Keywords are semantic anchors, not a fabricated exact model response.
        for label, content in (("transcript", transcript), ("note", note.decode()), ("thread", thread.decode())):
            if any(word.casefold() not in content.casefold() for word in words):
                raise RuntimeError("real " + label + " missing supplied semantic anchors; inspect private output")
        if (f'source_sha256: "{digest}"' not in note.decode()
                or f'request_id: "{job["request_id"]}"' not in note.decode()
                or f'thread_id: "{job["thread_id"]}"' not in note.decode()
                or "[[" + str(Path(job["note_path"]).with_suffix("")) + "]]" not in thread.decode()):
            raise RuntimeError("real generated identity/source/thread link mismatch")
        mark("actual ASR transcript and model-generated note/thread preserve known-speech meaning")
        mark("spool/archive bytes and SHA-256 match submitted synthetic speech")
        validator = subprocess.run([str(executable.with_name("voice-vault-lint")), "--vault", str(vault)],
                                   cwd=root, env=env, capture_output=True, text=True, timeout=10)
        (root / "validator.log").write_text(validator.stdout + validator.stderr)
        if validator.returncode or "0 findings" not in validator.stdout:
            raise RuntimeError("installed validator rejected real output; inspect private validator.log")
        mark("installed whole-vault validator accepts actual generated outputs")
        head = git(remote, "rev-parse", "refs/heads/main").strip().decode()
        standalone = subprocess.run([str(executable.with_name("voice-note-vault-sync"))], cwd=root,
                                    env=env, capture_output=True, text=True, timeout=30)
        (root / "publication.log").write_text(standalone.stdout + standalone.stderr)
        if standalone.returncode or git(repo, "rev-parse", "HEAD").strip().decode() != head:
            raise RuntimeError("installed standalone publication retry failed")
        mark("installed standalone publication verifies exact disposable remote HEAD")
        status, event = request_json(fixture.base_url + "/notify/json")
        if (status != 200 or event["id"] != job["notification_event_id"]
                or event["title"] != "Voice note completed" or job["note_path"] not in event["message"]
                or f"Request: {job['request_id']}" not in event["message"]
                or f"Thread: {job['thread_id']}" not in event["message"]
                or len(publication_at_notify) != 1 or state.calls != {"asr": 0, "llm": 0, "notify": 1}
                or sentinel.read_bytes() != b"# Disposable baseline\n"):
            raise RuntimeError("real notification outcome/order or disposable boundary mismatch")
        mark("controlled notification captured/read back exact ID after exact remote note/thread bytes")
        (root / "review.json").write_text(json.dumps({"transcript": transcript, "note": note.decode(),
             "thread": thread.decode(), "event": event, "publication_at_notification": publication_at_notify}, indent=2) + "\n")
        status, threads = request_json(base + "/v1/threads?limit=10")
        if status != 200 or len(threads["threads"]) != 1 or threads["threads"][0]["latest_status"] != "completed":
            raise RuntimeError("real recent thread API not completed")
    finally:
        service.terminate()
        try:
            service.wait(timeout=5)
        except subprocess.TimeoutExpired:
            service.kill()
            service.wait(timeout=5)
        log.close()
        fixture.close()
    with sqlite3.connect(f"file:{state_dir / 'jobs.sqlite3'}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = dict(db.execute("SELECT * FROM jobs WHERE request_id = ?", (job["request_id"],)).fetchone())
        if (row["status"] != "completed" or row["note_sha256"] != hashlib.sha256(note).hexdigest()
                or row["notification_event_id"] != event["id"] or not row["completed_at"]):
            raise RuntimeError("real durable SQLite/note hash/event mismatch after process stop")
    mark("durable completion, stored note hash and notification event survive process stop")
    return {"audio_sha256": digest, "audio_bytes": len(audio), "note_sha256": row["note_sha256"],
            "remote_head": head, "retry_count": row["retry_count"], "installed": installed,
            "notification": "controlled loopback capture; not phone delivery", "fallback_tested": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path,
                        help="installed voice-note-intake executable in the clean venv")
    parser.add_argument("--work-dir", type=Path,
                        help="private parent directory for retained disposable run files/logs")
    parser.add_argument("--evidence", type=Path,
                        help="write private result JSON (includes absolute run paths)")
    parser.add_argument("--real-audio", type=Path,
                        help="opt into real ASR/LLM using consented nonprivate known-speech WAV")
    parser.add_argument("--expect-words", nargs="+",
                        help="semantic anchors required in actual transcript, note and thread")
    parser.add_argument("--real-timeout", type=float, default=180,
                        help="bounded real job poll deadline in seconds")
    args = parser.parse_args()
    if args.real_audio and (not args.work_dir or not args.evidence or not args.expect_words):
        parser.error("--real-audio requires private --work-dir/--evidence and --expect-words")
    executable = args.executable.resolve()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.work_dir:
        parent = args.work_dir.resolve()
        parent.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="controlled-intake-", dir=parent))
    else:
        temporary = tempfile.TemporaryDirectory(prefix="controlled-intake-")
        root = Path(temporary.name)
    try:
        real_result = None
        if args.real_audio:
            real_result = check_real(executable, root, args.real_audio.resolve(), args.expect_words, args.real_timeout)
        else:
            check(executable, root)
        report = {
            "result": "PASS",
            "controlled_upstreams": not bool(args.real_audio),
            "real_inference": bool(args.real_audio),
            "real_result": real_result,
            "real_phone_delivery": False,
            "checks": CHECKS,
            "observations": OBSERVATIONS,
            "validator_cases": VALIDATOR_CASES,
            "sync_cases": SYNC_CASES,
            "run_directory": str(root),
        }
        print(json.dumps(report, indent=2))
        if args.evidence:
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0
    except Exception as error:
        report = {
            "result": "FAIL",
            "controlled_upstreams": not bool(args.real_audio),
            "real_inference": bool(args.real_audio),
            "real_phone_delivery": False,
            "checks": CHECKS,
            "observations": OBSERVATIONS,
            "validator_cases": VALIDATOR_CASES,
            "sync_cases": SYNC_CASES,
            "run_directory": str(root),
            "failure": str(error),
        }
        print(json.dumps(report, indent=2), file=sys.stderr)
        if args.evidence:
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.work_dir:
            print(f"private run files retained under: {root}", file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

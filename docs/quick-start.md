# Quick start

Linux, Python 3.13+. Dependencies in `pyproject.toml`. No Hermes needed. Intake does not install models. Provide writable state, archive, and note directories, plus compatible speech-recognition, language-model, and ntfy services. Below, ASR means speech recognition; LLM means language model; vault means note directory.

Default tests use local substitutes, no GPU. Real-inference tests still receive notifications locally. Neither tests phone delivery.

## Install

Install Git, curl, Python 3.13+, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Install outside source. No system Python changes, service installation, or `ensurepip` needed.

```sh
git clone https://github.com/dpotts34/local-voice-notes.git
cd local-voice-notes
SOURCE_DIR="$(pwd -P)"
uv venv --python python3.13 "$HOME/.local/venvs/voice-note-intake"
uv pip install --python "$HOME/.local/venvs/voice-note-intake/bin/python" "$SOURCE_DIR"
uv pip check --python "$HOME/.local/venvs/voice-note-intake/bin/python"
```

Already cloned? Start with `cd` into the root. Installing a wheel package? Replace `"$SOURCE_DIR"` with its path. Without uv, use `python3.13 -m venv`, then that environment's `python -m pip install`. Requires venv/ensurepip support.

First [verify installation](#verify-the-installation). Builds a fresh package and tests upload-to-note flow with local substitutes. Proves intake works, not your real services.

Endpoint requirements:

- ASR accepts multipart audio and returns JSON with nonempty `text`.
- LLM accepts OpenAI-compatible chat-completions requests and returns the required note JSON.
- ntfy returns an event ID when publishing to a topic.

Use audio your ASR accepts. Intake saves and forwards it unchanged.

## Configure and start

Create archive and vault directories. Obsidian optional. Copy the settings file. Edit URLs, model, and paths before starting. Empty required values stop startup.

```sh
mkdir -p "$HOME/.config/voice-note-intake" \
  "$HOME/.local/share/voice-note-intake/archive" \
  "$HOME/Documents/Obsidian"
# State contains private recordings and job data. For an existing directory,
# change permissions only if you own it and selected it for this service.
mkdir -p -m 700 "$HOME/.local/state/voice-note-intake"
chmod 700 "$HOME/.local/state/voice-note-intake"
cp "$SOURCE_DIR/deploy/voice-note-intake.env.example" \
  "$HOME/.config/voice-note-intake/env"
chmod 600 "$HOME/.config/voice-note-intake/env"
# Edit the env file: set your endpoint URLs, model, and paths.
set -a
. "$HOME/.config/voice-note-intake/env"
set +a
"$HOME/.local/venvs/voice-note-intake/bin/voice-note-intake"
```

Default address `127.0.0.1:8791`. `GET /health` returns `200` when state, upload storage, archive, vault/inbox, database, and worker are ready. It does not check upstream services. Startup errors name missing settings.

Leave intake running. Check health in another terminal:

```sh
curl --fail-with-body http://127.0.0.1:8791/health
```

`VOICE_REQUIRE_NFS_MOUNT=false` permits local archives. Set `true` to require an `nfs`/`nfs4` network-filesystem mount for readiness and writes. The archive directory must itself be the mount, not a subdirectory.

Phones cannot reach loopback. Set `VOICE_BIND_HOST` to a private interface address. Restrict access with a firewall. No built-in authentication, TLS, or access controls. Never expose intake to the internet or untrusted networks.

## Upload and check status

New recording, new canonical UUID. New thread, same UUID for `thread_id`. Unclear upload result? Retry identical saved audio with its original request ID.

```sh
REQUEST_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
curl --fail-with-body -F "audio=@recording.wav;type=audio/wav" \
  -F "request_id=$REQUEST_ID" -F "thread_id=$REQUEST_ID" \
  http://127.0.0.1:8791/v1/voice-notes
curl --fail-with-body "http://127.0.0.1:8791/v1/jobs/$REQUEST_ID"
curl --fail-with-body 'http://127.0.0.1:8791/v1/threads?limit=10'
```

HTTP `202` means audio and SQLite job saved, not completed. Poll for `completed` or `failed`. Notes are create-only in `Voice Inbox/`. No unrelated files overwritten. `Voice Threads/<thread_id>.md` groups notes. Shared thread IDs do not give the LLM earlier conversation.

Completion/failure notifications contain a note path and summary, no audio or transcript. ntfy event-cache lookup reduces duplicates. No idempotency key, duplicates remain possible after cache expiry/truncation. Saved event IDs do not prove phone delivery.

Default `VOICE_MAX_RETRIES=3` covers failures across archive, ASR, formatting, writing, and completion notification combined. Delay `min(2**retry_count, 60)` seconds.

Completion notification unavailable? Job stays `writing`. Retries check and reuse the note. Exhausted budget marks `failed`, even with a valid note. Audio and note remain. Failure notifications retry with backoff/idle polling across restarts until an event ID is saved. No cap or deadline. Restored notifications do not complete failed jobs. No exactly-once guarantee.

## Validate the vault

Installed package includes the read-only validator, PyYAML, and markdown-it-py. No source checkout, Hermes, service settings, or fixed vault name needed.

```sh
"$HOME/.local/venvs/voice-note-intake/bin/voice-vault-lint" \
  --vault /absolute/canonical/path/to/YourVault
```

Select the existing vault root, not `Voice Inbox/` or `Voice Threads/`. Use its full canonical path. Rejects relative paths, `..`, symlink roots/ancestors, filesystem root, and individual-note selectors. Reports descendant symlink directories and symlink/nonregular Markdown files without following them.

Checks all visible Markdown for YAML, tags, headings, and case collisions. Direct `Voice Inbox/` and `Voice Threads/` files also get filename, timestamp, and thread-link checks. Excludes hidden files/directories and exempts Excalidraw content. Unrelated invalid notes can block Git upload. Only voice files can be written or staged.

Exit `0`, no findings. Exit `1`, note paths and problems. Exit `2`, invalid path or command. Changes no files. Runs no Git. Git upload uses the same validator.

## Optional vault Git upload

Default `VOICE_VAULT_SYNC=false`, no remote access or inferred remote. Install Git. Choose an existing dedicated note checkout and remote branch, never this source checkout. Vault may be the checkout root or any visible subdirectory. Both paths must be absolute, canonical, and existing, without symlink ancestors or `..`. Rejects bare, linked-worktree, nested checkouts, and vault paths in Git metadata.

```sh
export VOICE_VAULT_SYNC=true
export VOICE_VAULT_REPO_DIR=/absolute/canonical/path/to/vault-checkout
export VOICE_VAULT_DIR=/absolute/canonical/path/to/vault-checkout/YourVault
export VOICE_VAULT_REMOTE=https://git.example.invalid/you/vault.git
export VOICE_VAULT_BRANCH=main
# Set Git identity in the selected checkout, not in global configuration:
git -C "$VOICE_VAULT_REPO_DIR" config user.name "Your Name"
git -C "$VOICE_VAULT_REPO_DIR" config user.email "you@example.invalid"
# Start intake with these plus the required ordinary intake environment settings.
# Or retry standalone publication using that same environment:
"$HOME/.local/venvs/voice-note-intake/bin/voice-note-vault-sync"
```

`VOICE_VAULT_REMOTE` requires an HTTPS/SSH URL or full canonical path to a local bare repository outside the checkout. No `origin` name or SCP shorthand. No source remote or private default key selected. `VOICE_VAULT_BRANCH` defaults to `main`. Checkout must be on that branch. Never put credentials in URLs.

Configure noninteractive credentials first. Git disables prompts, system/global config, environment overrides, and local hooks. HTTPS needs a repository-local credential helper or other preconfigured authentication. Optional `VOICE_VAULT_GIT_SSH_KEY` must name a canonical regular file. SSH quotes the path and uses batch mode with `IdentitiesOnly=yes`. Without it, normal noninteractive SSH authentication applies.

Upload checks the whole vault, protects pending changes in a temporary stash, permits only allowed fast-forwards, pushes without force, and verifies the exact remote branch commit. Stages only direct visible `.md` files with generated identity headers in `Voice Inbox/` and `Voice Threads/`. Other notes get checked, not staged. Never stashes or stages the writer's untracked `Voice Inbox/.write.lock`. Keeps user stashes.

Rejects local deletions, unrelated staged/unstaged/untracked/renamed files, unrelated incoming/outgoing commits even if reverted, diverged histories, invalid notes, active Git operations, and source-checkout targets.

Worker uploads before completion notification. Sync failure keeps note/audio, reports `lint_or_sync`, and consumes shared retries. Failure notifications prove neither completion nor upload. Health does not check the remote or verify upload. Each Git command has a 60-second limit, not a total-job deadline. Stop other editors/Git clients during upload. Locks coordinate intake processes only.

### Git recovery

Interrupted stash? Intake keeps it and `VOICE_STATE_DIR/vault-sync-recovery.json`. Upload stops until manual recovery. Record names paths, phase, stash, local commit/error. A crash can leave phase `stashing` without a stash ID. Check `git stash list` and its reflog. Missing ID does not mean nothing was saved.

Failed fetch/file-scope checks try to restore pending files/index, but keep the stash. Resolve conflicts manually. Allowed fast-forwards/local commits can remain after later check/push/verification failures. No destructive rollback, reset, clean, force push, or deletion of conflicted data.

To recover:

1. Stop intake. Back up repository, private recovery record, conflicted worktree/index, and stash. Inspect with `git stash show --include-untracked --patch <stash-object>`.
2. Check record, `git status`, and `git stash list`. Resolve/apply the stash in the selected repository. Fix note checks, file scope, and diverged histories. Compare local HEAD with the selected remote branch.
3. Verify all content recovered before `stash pop` or dropping stashes.
4. Then archive/remove the recovery record and restart/retry. Keep backups. Failed jobs stay failed.

## Retention and scope

Default archive cap 5 GiB, `VOICE_ARCHIVE_MAX_BYTES=5368709120`. No age expiry. Deletes oldest tracked completed originals first, never active, failed, unresolved, or untracked recordings. Not a filesystem quota. Total use can exceed it. Job endpoint reports deletions. State, upload storage, transcripts, and notes remain.

Set the cap, monitor disk use, and back up state, archive, and vault separately. Checks and uploads use your selected vault. Git upload defaults off. Never use the source-repository remote.

## Verify the installation

[Installed-package test](../tests/check_installed_intake.py). HTTP upload to notes, with local ASR/LLM/notification substitutes.

From source root, build/install outside source:

```sh
SOURCE_DIR="$(pwd -P)"
CHECK_TMP="$(mktemp -d)"
uv build --wheel --out-dir "$CHECK_TMP/dist" "$SOURCE_DIR"
uv venv --python python3.13 "$CHECK_TMP/venv"
uv pip install --python "$CHECK_TMP/venv/bin/python" "$CHECK_TMP"/dist/*.whl
uv pip check --python "$CHECK_TMP/venv/bin/python"
"$CHECK_TMP/venv/bin/python" "$SOURCE_DIR/tests/check_installed_intake.py" \
  --executable "$CHECK_TMP/venv/bin/voice-note-intake" \
  --work-dir "$CHECK_TMP/runs" --evidence "$CHECK_TMP/controlled-e2e.json"
```

Temporary loopback services and disposable paths. Tests abrupt restart after HTTP `202`, duplicate IDs with same/different audio, ASR/LLM `503` outages, invalid note JSON, notification failure/cache recovery, protected-output refusal, and zero-cap retention with unfinished/failed/unresolved recordings. Failure scenarios use `VOICE_MAX_RETRIES=2`. Also tests 27 validator cases and local Git upload, including rejection, recovery, and HTTP worker flow.

Success exits `0`, writes JSON `"result": "PASS"`. Proves local test behavior, not real inference or phone delivery. Keep `CHECK_TMP` outside source. `mktemp` honors `TMPDIR`. Retain JSON/logs for failures. Paths, logs, state, and stashes are private. Do not commit them. Without uv, use `python3.13 -m venv` and that environment's `python -m pip install`, with ensurepip support.

### Optional real-inference test

Reuse the installed package/check. Choose real ASR/LLM services and approved, nonprivate WAV speech. Synthetic speech works. Silence/private recordings do not. Match key words, not exact transcript/title. Example reminder to return library books tomorrow, match `return library books`. Review time meaning manually. "The next day" may mean "tomorrow".

```sh
export VOICE_ASR_URL='http://<your-asr-service>/v1/audio/transcriptions'
export VOICE_LLM_URL='http://<your-llm-service>/v1/chat/completions'
export VOICE_LLM_MODEL='<your-loaded-model>'
export VOICE_HTTP_TIMEOUT=60 VOICE_LLM_PRIMARY_TIMEOUT=60
"$CHECK_TMP/venv/bin/python" "$SOURCE_DIR/tests/check_installed_intake.py" \
  --executable "$CHECK_TMP/venv/bin/voice-note-intake" \
  --real-audio /private/path/to/synthetic-known-speech.wav \
  --expect-words return library books --real-timeout 180 \
  --work-dir "$CHECK_TMP/real-runs" --evidence "$CHECK_TMP/real-e2e.json"
```

Real mode sends unchanged WAV through installed `ExternalClients` and the actual LLM prompt/schema. No fake inference or inherited backup model, live output/topic, credentials, or Git settings. Uses isolated loopback, private state, a differently named canonical vault, and dedicated local bare Git remote.

Local notification receiver requires exact remote commit and note/thread bytes before completion. Saves the event for exact-ID verification. Installed validator, standalone upload retry, and SQLite check after shutdown must pass. Stops at two processing failures or the polling deadline. Real-service failures block acceptance. Substitutes cannot replace real inference.

Evidence is private, including synthetic audio, transcripts, notes/threads, service settings, logs, and full paths. Publish only reviewed checksums, environment, redacted command templates, results, and limits. Tests WAV on selected services, not iPhone codecs/uploads, Shortcuts, external ntfy, phone display, backup models, NFS, or live deployment.

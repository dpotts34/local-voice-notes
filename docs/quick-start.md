# Quick start

This release tree supports the durable voice-note intake service on Linux with Python 3.13 or later. Runtime Python dependencies are declared in `pyproject.toml`; no Hermes installation or GPU/runtime installer is required on the intake host. You need writable local state, an archive directory, an output vault, and compatible ASR, structured-LLM, and ntfy HTTP endpoints.

The default acceptance mode uses controlled endpoints and is not real inference or phone-delivery evidence. The same check has an opt-in real-ASR/LLM mode below; it still captures notifications locally and does not test a phone. A real installation needs your own endpoint implementations and model choices.

## Install

Install the built release wheel into a dedicated environment outside the source tree. Alternatively, the package path may be a checked-out release tree. This does not install a system service or modify system Python:

```sh
python3.13 -m venv "$HOME/.local/venvs/voice-note-intake"
"$HOME/.local/venvs/voice-note-intake/bin/python" -m pip install /path/to/voice_note_intake-0.1.0-py3-none-any.whl
# Without ensurepip: uv venv --python python3.13 "$HOME/.local/venvs/voice-note-intake"
# Then: uv pip install --python "$HOME/.local/venvs/voice-note-intake/bin/python" /path/to/release.whl
```

The ASR service must accept multipart audio at the configured URL and return JSON with a nonempty `text`. The LLM endpoint must implement the OpenAI-compatible chat-completions request and return the required structured note JSON. The notification URL is an ntfy topic endpoint whose publish response includes an event ID. Choose audio formats accepted by your ASR service; intake archives and forwards the original upload unchanged.

## Configure and start

Create the directories you chose for the archive and vault, then copy the example environment file and edit it. All endpoint/model values and the archive/vault paths are required; empty placeholders intentionally fail startup.

```sh
mkdir -p "$HOME/.config/voice-note-intake" \
  "$HOME/.local/share/voice-note-intake/archive" \
  "$HOME/Documents/Obsidian"
# State contains private recordings and job data. For an existing directory,
# change permissions only if you own it and selected it for this service.
mkdir -p -m 700 "$HOME/.local/state/voice-note-intake"
chmod 700 "$HOME/.local/state/voice-note-intake"
cp /path/to/voice-note-intake/deploy/voice-note-intake.env.example \
  "$HOME/.config/voice-note-intake/env"
# Edit the env file: set your endpoint URLs, model, and paths.
set -a
. "$HOME/.config/voice-note-intake/env"
set +a
"$HOME/.local/venvs/voice-note-intake/bin/voice-note-intake"
```

The default listener is `127.0.0.1:8791`; `GET /health` returns `200` only when state, spool, archive, vault/inbox, database, and worker are ready. Readiness reports upstreams as unprobed; it does not promise that inference endpoints are reachable. Missing required settings produce a startup error naming the setting.

`VOICE_REQUIRE_NFS_MOUNT=false` is the intentional local-directory archive mode. To require NFS, set it to `true`: readiness and archive writes then require the configured archive directory itself to be an `nfs`/`nfs4` mount. A normal directory beneath a mount-looking path does not satisfy that check.

For a phone or another trusted LAN client, loopback is not reachable remotely. Set `VOICE_BIND_HOST` to the service host's private interface address and restrict access with the host/network firewall. This service has no application-layer authentication; do not expose it to the public internet or an untrusted network. There is no built-in TLS or access-control layer.

## Upload and check status

Use a new canonical UUID for each new recording. For a new thread, use that same UUID as `thread_id`. Reuse a request ID only to retry the exact same retained audio after an ambiguous upload result.

```sh
REQUEST_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
curl --fail-with-body -F "audio=@recording.wav;type=audio/wav" \
  -F "request_id=$REQUEST_ID" -F "thread_id=$REQUEST_ID" \
  http://127.0.0.1:8791/v1/voice-notes
curl --fail-with-body "http://127.0.0.1:8791/v1/jobs/$REQUEST_ID"
curl --fail-with-body 'http://127.0.0.1:8791/v1/threads?limit=10'
```

The upload returns HTTP `202` after the original audio and SQLite job are durable. It does not mean transcription/note creation is complete. Poll the job endpoint for `completed` or `failed`. Notes are create-only under the exact vault-relative `Voice Inbox/`; the service will not overwrite an existing unrelated file. A `Voice Threads/<thread_id>.md` index groups notes by ID, but ID reuse does not provide conversation history to the LLM.

Completion/failure notifications include a note path and concise summary, not raw audio or transcript. Cached-history recovery reduces duplicate delivery, but ntfy does not provide an idempotency key; cache expiry/truncation can leave a duplicate-delivery window. A published event ID does not prove that a phone received or displayed it.

`VOICE_MAX_RETRIES` defaults to `3`: this is the shared count of processing failures across archive, ASR, formatting, writing, and completion notification, not three attempts per stage. Retries wait `min(2**retry_count, 60)` seconds. A completion-notification outage leaves the job in `writing` with its already-created note; retry verifies/reuses that note instead of generating another. Exhausting the shared failure budget makes the job `failed`, even if a valid note was already written. Its audio and note remain available. Delivery of the **failure** notification has no separate attempt cap or deadline: it continues with backoff/idle polling, including after process restart, until an event ID is saved. Restoring notification service does not change a failed job back to completed. There is no exact-once guarantee.

## Validate the vault

The installed package includes the existing read-only validator and its PyYAML/markdown-it-py dependencies. Run it from any directory; no source checkout, Hermes interpreter, service configuration, or fixed vault name is required:

```sh
"$HOME/.local/venvs/voice-note-intake/bin/voice-vault-lint" \
  --vault /absolute/canonical/path/to/YourVault
```

Select the vault itself, not `Voice Inbox/` or `Voice Threads/`. The explicit root must already exist and be absolute/canonical: relative paths, `..`, symlink roots/ancestors and the filesystem root are refused rather than silently resolved. No absolute or relative per-note selectors are accepted. Descendant symlink directories and Markdown files and nonregular Markdown files are reported without following them.

Validation retains the original **whole-vault** scope: all visible Markdown notes receive YAML/tag/heading/case-collision checks, with additional filename, timestamp and thread-link rules for direct `Voice Inbox/` and `Voice Threads/` members. Hidden files/directories remain excluded, and Excalidraw content remains exempt as before. An unrelated invalid note can therefore fail validation; this is intentional preservation of the previous lint-before-publication boundary, not an expansion of writable/stageable paths. The service still writes only to the existing voice directories.

Exit `0` means no findings; exit `1` lists actionable note paths/reasons; exit `2` reports an invalid boundary or invocation. Validation never changes files or runs Git. Opt-in publication below invokes this same installed validator.

## Opt-in vault Git publication

Publication is disabled by default (`VOICE_VAULT_SYNC=false`); no remote is inferred or contacted. Git must be installed. Choose an existing **dedicated vault checkout**, not this project's source checkout, and an existing remote branch. The vault may be the repository root or a differently named visible subdirectory within it. Both paths must be existing absolute canonical directories, without symlink ancestors or `..`. Bare/worktree-indirected/nested checkouts and Git-metadata vault targets are refused.

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

`VOICE_VAULT_REMOTE` is required: an explicit HTTPS/SSH URL (not an `origin` name or SCP shorthand), or an absolute canonical local **bare** repository outside the selected checkout. No source-repository remote or private default key is selected. `VOICE_VAULT_BRANCH` defaults to `main`; checkout must be attached to that branch. Configure credentials before starting; Git terminal prompts, system/global Git config, ambient Git overrides, and local hooks are disabled for these operations. HTTPS auth therefore needs a repository-local credential helper or another preconfigured noninteractive mechanism. Optional `VOICE_VAULT_GIT_SSH_KEY` selects an explicit canonical regular file; it is passed as a quoted SSH argument with batch mode and `IdentitiesOnly=yes`. Without it, normal noninteractive SSH authentication applies. Do not embed credentials in remote URLs.

The syncer retains full-vault lint before publication, temporary-stash protection, allowed fast-forward only, a normal non-force push, and exact remote branch HEAD read-back. Only direct visible `.md` files under `Voice Inbox/` and `Voice Threads/` with generated identity headers are stageable; local deletions are refused. Unrelated staged, unstaged, untracked and renamed paths, unrelated incoming/outgoing commits (even followed by reverts), divergence, invalid notes, active Git operations, and source-checkout targets are refused. The writer's exact untracked `Voice Inbox/.write.lock` is never stashed/staged. Normal notes elsewhere in the vault are linted but never staged. Preexisting user stashes are not discarded.

The worker publishes **before** completion notification. A sync failure leaves an already-written note and retained audio, uses `lint_or_sync`, and consumes the existing shared retry budget. A terminal failure notification is not a completion notification or proof of publication. Health readiness does not probe remote connectivity or prove publication. Git subprocesses are bounded to 60 seconds individually, not a total-job deadline. Keep checkout Git access exclusive while intake publishes; its locks coordinate only intake processes, not other editors/Git clients.

### Publication recovery

After any failure with temporary stashed data, `VOICE_STATE_DIR/vault-sync-recovery.json` and the stash are preserved; subsequent publication refuses until an operator resolves recovery. The record names the selected boundary, phase, stash object and local head/error. A crash during the stash command may leave the `stashing` record without a stash ID: inspect `git stash list` and its reflog, do not assume nothing was saved. Failed fetch/scope checks try to restore pending bytes/index without dropping the stash. Restore conflicts are not automatically resolved. A permitted remote fast-forward or successful local commit can remain after a later lint/push/read-back failure; there is no destructive rollback, reset, clean, force push, or automatic dropping of conflicted data.

Stop intake before recovery. Back up the repository, private state record, conflicted worktree/index, and referenced stash (`git stash show --include-untracked --patch <stash-object>`). Inspect the record and `git status`/`git stash list`; resolve or manually apply the preserved stash in the selected repository, fix lint/scope/divergence, and compare local HEAD with the explicit remote branch. Do not use `stash pop` or drop any stash before saved content has been recovered and verified. Only after recovery is complete, archive/remove the recovery record and restart/retry. Preserve the backup evidence; a failed job stays failed and must not be relabeled completed just because Git later recovers.

## Retention and scope

The archive cap defaults to 5 GiB (`VOICE_ARCHIVE_MAX_BYTES=5368709120`) with no age expiry. It caps the tracked **completed** originals, deleting the oldest eligible completed originals first; it is not a hard filesystem quota. Active, failed, and unresolved/untracked recordings are excluded and can keep total disk use above the cap. Deletion outcomes are exposed by the job endpoint. Local state, spooled audio, transcripts, and notes are not removed by this policy. Set the cap to the value appropriate for your retention policy, monitor total disk use, and back up state/archive/vault separately.

Read-only validation and opt-in Git publication use the explicitly selected vault boundary. Publication is off by default; never select a source-repository remote.

The installed-distribution controlled acceptance check is [`../tests/check_installed_intake.py`](../tests/check_installed_intake.py). It validates the complete HTTP flow against local controlled ASR/LLM/notification fixtures; it is not a substitute for acceptance against real inference services.

To build and install outside the release tree, then run the single high-level check:

```sh
CHECK_TMP="$(mktemp -d)"
uv build --wheel --out-dir "$CHECK_TMP/dist" /path/to/voice-note-intake
python3.13 -m venv "$CHECK_TMP/venv"
"$CHECK_TMP/venv/bin/python" -m pip install "$CHECK_TMP"/dist/*.whl
"$CHECK_TMP/venv/bin/python" /path/to/voice-note-intake/tests/check_installed_intake.py \
  --executable "$CHECK_TMP/venv/bin/voice-note-intake" \
  --work-dir "$CHECK_TMP/runs" --evidence "$CHECK_TMP/controlled-e2e.json"
```

The check uses only ephemeral loopback fixture endpoints and fresh disposable paths. It includes abrupt restart after HTTP 202, identical/different-audio duplicate retries, controlled ASR/LLM HTTP 503 outages, invalid structured responses, notification failures/history recovery, protected-output refusal, and zero-cap retention with unfinished/failed/unresolved recordings. `VOICE_MAX_RETRIES=2` bounds the controlled failure scenarios. It also checks 27 installed-validator cases and publication against disposable local bare remotes (including refusal/recovery cases and the HTTP worker). Its JSON evidence labels controlled endpoints, not real inference or confirmed phone delivery; retained logs/state/stashes and absolute run paths are private evidence, not publication artifacts.

On systems without Python's `ensurepip`/venv package, use `uv venv --python python3.13 "$CHECK_TMP/venv"` and `uv pip install --python "$CHECK_TMP/venv/bin/python" "$CHECK_TMP"/dist/*.whl` instead of the two venv/pip commands above. Keep `CHECK_TMP` outside the release tree; `mktemp` honors your configured `TMPDIR`.

### Opt-in real-inference acceptance

Reuse the same external wheel installation and high-level check. Supply only operator-selected real ASR/LLM endpoints and a consented nonprivate known-speech WAV (a synthetic spoken reminder is suitable, silence is not). Do not use a private user recording. Choose semantic words present in the known speech rather than assuming an exact transcription/title. For example, a synthetic request to return library books tomorrow can use `return library books`; inspect temporal meaning manually because summaries may paraphrase tomorrow as the next day.

```sh
export VOICE_ASR_URL='http://<your-asr-service>/v1/audio/transcriptions'
export VOICE_LLM_URL='http://<your-llm-service>/v1/chat/completions'
export VOICE_LLM_MODEL='<your-loaded-model>'
export VOICE_HTTP_TIMEOUT=60 VOICE_LLM_PRIMARY_TIMEOUT=60
"$CHECK_TMP/venv/bin/python" /path/to/voice-note-intake/tests/check_installed_intake.py \
  --executable "$CHECK_TMP/venv/bin/voice-note-intake" \
  --real-audio /private/path/to/synthetic-known-speech.wav \
  --expect-words return library books --real-timeout 180 \
  --work-dir "$CHECK_TMP/real-runs" --evidence "$CHECK_TMP/real-e2e.json"
```

Real mode forwards the original WAV through the installed `ExternalClients` ASR client and the actual structured-output LLM prompt/schema. It does not serve controlled ASR/LLM responses and does not inherit fallback, production output/topic, credentials or publication settings. It creates an isolated loopback listener, private state, differently named canonical vault, and dedicated local bare Git remote. Only a loopback notification fixture is used: it refuses completion until the exact remote HEAD and note/thread bytes match, then captures the event for exact-ID read-back. Installed validation, standalone publication retry and read-only SQLite verification after process stop must pass. Two processing failures and the specified poll deadline bound the run; a real endpoint failure is a blocker, never a controlled-inference substitute.

All retained evidence is **private**, including synthesized media, transcripts, note/thread contents, endpoint configuration, logs and absolute paths. Publish only an allowlisted summary of artifact/source-tree digests, environment, sanitized command templates, check outcomes and limits. This run tests WAV on the selected services, not an iPhone recording codec, Shortcut/device transport, external ntfy service, phone display, fallback model, NFS or a production deployment.

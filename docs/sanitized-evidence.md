# Issue 9: real-inference clean-install acceptance

**Real installed flow PASS** and **116 controlled high-level checks PASS**. **176 preserved checks completed passing**, with five explicit exclusions: three obsolete private deployment contracts and two unsupported subsecond timing expectations. This is not an all-181 legacy-suite PASS.

## Artifact and environment

- Wheel: `voice_note_intake-0.1.0-py3-none-any.whl`; SHA-256 `a611f42310c326d0296af87cdd9200a239c0ee73af5fd593ab2e14befee4c96a`. Final rebuild is byte-identical to the installed artifact and issue-6 frozen wheel.
- Source tree SHA-256: `ac8e04ceef1fde97cc848d0d64aa096d519785a5556cfdd3b9cacc928e946baf`. Unversioned candidate; no release Git history initialized. Relative-file manifest and digest algorithm are in `sanitized-evidence.json`.
- Linux `6.12.100+deb13-amd64`, Python 3.13.5, uv 0.11.2, ffmpeg 7.1.5. Runtime dependencies installed normally in a fresh external venv. No source checkout or Hermes dependency in the listener. Existing pytest tooling was installed only in a separate external environment.

## Verified boundaries

Consented synthetic nonprivate speech went through real ASR and the installed client's actual structured LLM prompt/schema. Actual transcript, note, thread summary and notification meaning were inspected, including reminder subject, requested return action and relative next-day timing. No output prose/media is included here.

Original submitted WAV bytes/hash matched durable spool/archive. Generated identity/thread links, installed whole-vault validator (three notes, zero findings), exact disposable remote HEAD/note/thread bytes, installed standalone publication retry, notification exact-event read-back and durable SQLite/note hash after shutdown all passed. Zero processing retries.

The loopback notification receiver independently required exact remote HEAD and both generated file bytes **before** accepting completion. This verifies publication ordering, not a deployed ntfy service or phone display. No active owned trial processes remained after cleanup.

## Repeat

`sanitized-evidence.json` contains build/install, real and controlled high-level command templates. Substitute operator-selected real endpoints/model and known nonprivate audio. Keep all env files, raw outputs and disposable repositories outside the source tree. Real mode inherits only explicitly selected primary ASR/LLM settings, never production archive/vault/topic/Git/fallback settings. Follow the quick-start's documented uv fallback where Debian Python lacks ensurepip and its mkdir/chmod private-state setup.

## Preserved checks and limitations

Nine original test files ran unchanged against the installed artifact, with cache/source-path contamination disabled. The 480-second aggregate bound retained 145 completed passes; only unfinished cases continued, with 31 passes in 95.22 seconds and no overlap. Earlier failed/timed-out runs remain private, not relabeled PASS. All five exclusions and exact reasons are in `sanitized-evidence.json`.

A legacy one-second ASR-start setup wait and a 0.1-second artificial lease were incompatible with measured 0.125–0.419-second fsync latency on this host; neither is a documented portable timing guarantee. Default worker ownership, other lease/fencing/cancellation checks and installed bounded cleanup passed. No runtime change was made to conceal those timing failures.

The first real trial completed but a literal temporal-token assertion rejected a genuine summary paraphrase. Documented semantic anchors were corrected and actual meaning reviewed. Streaming TTS WAV headers were normalized with ffmpeg before the final run; both attempts were retained.

No iPhone/Shortcut/device transport, phone notification display, fallback-model or real NFS claim is made. This verifies only the submitted synthetic WAV codec on selected services. No production deployment, network/service change, personal-vault/production-topic write, public repository/push, license selection or issue closure occurred. iPhone guidance remains generic and explicitly device-untested.

Only the existing acceptance checker and two documentation files changed; all runtime sources match the frozen baseline. No real-inference prerequisite blocker remains. Parent specification/quality review is required before issue closure.

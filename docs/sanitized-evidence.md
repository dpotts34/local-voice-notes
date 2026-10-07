# Earlier installed-package tests

Historical issue-9 results, not a test of the current release or your services.

Real inference passed. Local test services passed 116 checks. Older tests passed 176 checks. Five excluded, three obsolete private-deployment contracts and two unsupported subsecond timing expectations. Not 181 passes.

## Artifact and environment

- Package `voice_note_intake-0.1.0-py3-none-any.whl`. SHA-256 `a611f42310c326d0296af87cdd9200a239c0ee73af5fd593ab2e14befee4c96a`. Rebuild matched the installed package and frozen issue-6 package.
- Source SHA-256 `ac8e04ceef1fde97cc848d0d64aa096d519785a5556cfdd3b9cacc928e946baf`. No release Git history at that time. [File list and checksum method](sanitized-evidence.json).
- Linux `6.12.100+deb13-amd64`, Python 3.13.5, uv 0.11.2, ffmpeg 7.1.5. Fresh external Python environment with normal dependencies. Listener used neither source imports nor Hermes. Older pytest tests used a separate environment.

## What passed

Approved synthetic speech used real speech recognition and the installed client's language-model prompt/schema. Reviewed transcript, note, thread summary, and notification preserved the reminder, return action, and next-day meaning. No recording or generated prose included.

Zero processing retries. Checks passed:

- Saved upload and archived WAV matched the input bytes and checksum.
- Generated identities and thread links matched.
- Installed note validator checked three notes, zero findings.
- Temporary Git remote matched the commit and note/thread bytes. Standalone upload retry passed.
- Notification read-back matched the event ID.
- Completed SQLite record and note checksum survived shutdown.

The local notification receiver required the Git commit and both output files before accepting completion. Proves upload order, not real ntfy or phone delivery. Cleanup left no owned test processes running.

## Repeat

[Command templates](sanitized-evidence.json). Supply your service URLs, model, and known nonprivate audio. Keep settings, raw output, and test repositories outside source. Real mode copies only selected primary speech-recognition and language-model settings, never live archive, vault, topic, Git, or backup-model settings. Use the [quick start](quick-start.md) for uv installation and private-directory permissions. uv avoids Debian's missing ensurepip.

## Older tests and limits

Nine unchanged test files used the installed package, without cached/source imports. A 480-second run completed 145 passes. Only unfinished tests continued, another 31 passes in 95.22 seconds. No overlap. Failed and timed-out runs remain private failures. [Five exclusions and reasons](sanitized-evidence.json).

The old one-second speech-recognition startup wait and artificial 0.1-second lease failed with measured fsync latency of 0.125 to 0.419 seconds. Neither timing is a portable guarantee. Default ownership, other lease/exclusive-access/cancellation tests, and bounded cleanup passed. Runtime stayed unchanged.

The first real job completed. A literal-word assertion rejected a valid time paraphrase. The check changed to test meaning, then passed human review. ffmpeg corrected streaming text-to-speech WAV headers before the final run. Both attempts retained.

Only the submitted synthetic WAV and selected services tested. No iPhone/Shortcut upload, phone display, backup model, or real network-file-system storage tested. iPhone instructions remained generic and device-untested.

At this run, no deployment, network/service change, personal-vault/live-topic write, public repository/push, license choice, or issue closure occurred.

Only the existing checker and two guides changed. Runtime matched the frozen baseline. Real-inference prerequisites met. Specification/quality review still needed before issue closure at that time.

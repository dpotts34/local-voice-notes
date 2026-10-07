# Historical release preparation

Old preparation record. Not current status. Start with the [README](README.md) or [quick start](docs/quick-start.md).

The maintainer later approved the [initial public commit](https://github.com/dpotts34/local-voice-notes/commit/b1a86e207862ca12c1c5b7fdf60be294c14d2ea8). An anonymous clone and identical package rebuild verified publication.

## Included components

- [Intake](README.md). Linux, Python 3.13+. User-selected speech-recognition, language-model, and notification services. Build from the repository root. Preserve `src/voice_note_intake`, which prevents note publication from a source checkout.
- [Speech proxies](proxies/README.md). Python standard library and FFmpeg. Local conversion/API tests only.
- [Native patch](patches/README.md). Applied to one NeMo-Speech.cpp revision. No GPU build or inference test.
- [Earlier test results](docs/sanitized-evidence.md) and [file manifest](docs/sanitized-evidence.json). Real speech recognition and language model, synthetic WAV, local notification receiver. Cover the tested intake files and package, not the later assembled release.

Single user. Loopback by default. No authentication or TLS. Never expose directly to the internet. No models, runtime binaries, recordings, notes, state, or deployment settings bundled.

## Approval state before publication

At this stage, publication was not approved. The maintainer confirmed personal ownership and Apache-2.0 for original work, including both proxies and the patch. Upstream terms remain separate. See [LICENSE](LICENSE), [NOTICE](NOTICE), and [credits](THIRD_PARTY_NOTICES.md).

Adding notices changed the package checksum, not runtime code. Earlier inference evidence still described the older package.

The maintainer selected `dpotts34/local-voice-notes`, identity `dpotts34 <65884710+dpotts34@users.noreply.github.com>`, and root commit message `Initial sanitized source release`. Source/package review passed. New history and its report still needed verification, then explicit publication approval. Component checks and local commits alone did not authorize publication.

# Local voice notes

Uploads become Markdown notes. Intake saves the audio, calls speech recognition and a language model, writes notes and thread indexes, then notifies through ntfy.

Single-user intake. Linux, Python 3.13+. Notes go in `Voice Inbox/`. Bring your own speech-recognition, language-model, and ntfy services. This project does not install models or inference servers.

## Start here

1. [Install and check](docs/quick-start.md#install). Local test services. No GPU or inference server needed.
2. [Configure and start](docs/quick-start.md#configure-and-start). Use compatible services. Keep settings outside source.
3. [Upload and check status](docs/quick-start.md#upload-and-check-status). HTTP `202` means received, not completed.
4. [Set up an iPhone Shortcut](docs/ios-shortcut.md) after a real upload works.

[Required settings](deploy/voice-note-intake.env.example). The quick start also covers note validation, optional Git upload, audio retention, and recovery.

## Optional components

- [Speech proxies](proxies/README.md). Separate Python/FFmpeg tools.
- [Native speech-recognition patch](patches/README.md). Checked against one upstream revision. No GPU build or inference claim.
- [Earlier test results](docs/sanitized-evidence.md). Historical evidence, not a test of your services or phone.

Develop reusable code here. Keep recordings, notes, credentials, settings, state, and private evidence outside source. Updating source does not deploy services.

## Safety and license

Loopback by default. No built-in authentication or TLS. Trusted private networks only. Never expose intake directly to the internet. Tests with local substitutes do not prove real inference or phone delivery.

Original code, docs, checks, proxies, and local patch contributions use [Apache-2.0](LICENSE). Copyright 2026 dpotts34. Upstream material keeps its own terms. See [NOTICE](NOTICE) and [credits](THIRD_PARTY_NOTICES.md). Models, external tools, and inference runtimes are not bundled and have separate licenses.

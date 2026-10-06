# Voice Note Intake

A portable, single-user service that durably accepts voice recordings, archives them, sends them to configured ASR and structured-LLM endpoints, writes create-only notes under `Voice Inbox/`, maintains thread indexes, and sends status notifications.

- [Quick start, configuration, API usage, retention, and limits](docs/quick-start.md)
- [Generic iPhone Shortcut setup](docs/ios-shortcut.md)
- [Example environment configuration](deploy/voice-note-intake.env.example)

The listener defaults to loopback. This release does not include application-layer authentication, model weights, or speech-service installers. Controlled E2E results are not real inference results.

Original project code, documentation, checks, proxies and local patch contributions are licensed under [Apache-2.0](LICENSE), copyright 2026 dpotts34. Existing upstream material retains its own licenses and attribution; see [NOTICE](NOTICE) and [third-party credits](THIRD_PARTY_NOTICES.md). Model weights, external tools and inference runtimes have separate terms and are not bundled.

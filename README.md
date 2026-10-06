# Local Voice Notes

A single-user service that turns uploaded recordings into durable Markdown notes:

```text
Recording → durable intake → ASR → structured LLM → Markdown note → ntfy notification
```

The supported first installation is **voice-note intake on Linux with Python 3.13+**. It archives the original audio, creates notes under `Voice Inbox/`, and maintains thread indexes. It does not install speech models or inference servers.

## Start here

1. [Clone, install, and run the controlled installation check](docs/quick-start.md#install). This needs no GPU or running inference service; the check uses local fixtures.
2. [Configure your own services and start intake](docs/quick-start.md#configure-and-start). Real use requires compatible ASR, structured-LLM, and ntfy endpoints. Keep their configuration outside this checkout.
3. [Upload a recording and check completion](docs/quick-start.md#upload-and-check-status). An HTTP 202 response means received, not completed.
4. [Set up an iPhone Shortcut](docs/ios-shortcut.md) after the real upload path works.

The [example environment file](deploy/voice-note-intake.env.example) lists the required settings. The quick start also covers vault validation, optional vault Git publication, retention, and failure recovery.

## Optional advanced components

- [Speech proxies](proxies/README.md): standalone Python/FFmpeg tools, separate from the intake installation.
- [Pinned native ASR patch](patches/README.md): upstream source instructions and retained license notices; patch application is verified, not universal GPU support.
- [Earlier real-inference acceptance and its limits](docs/sanitized-evidence.md): historical evidence, not a test of your endpoints or phone.

The public repository is the source home for reusable code and installation instructions. Keep recordings, generated notes, credentials, personal configuration, state, and private evidence outside it. Deploying a service is a separate action from updating source.

## Safety and license

The listener defaults to loopback. There is no application-layer authentication or built-in TLS: use only a trusted private network, never direct internet exposure. Controlled E2E results are not real inference or phone-delivery results.

Original project code, documentation, checks, proxies and local patch contributions are licensed under [Apache-2.0](LICENSE), copyright 2026 dpotts34. Existing upstream material retains its own licenses and attribution; see [NOTICE](NOTICE) and [third-party credits](THIRD_PARTY_NOTICES.md). Model weights, external tools and inference runtimes have separate terms and are not bundled.

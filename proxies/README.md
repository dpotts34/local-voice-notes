# Speech proxies

Optional tools, not first-install requirements. Two Python HTTP proxies and one local test. No service units, models, private records, credentials, or media.

## Requirements

- Python 3.10+. Standard library only.
- Executable FFmpeg on `PATH` or at an explicit path.
- FFmpeg must read submitted formats. Tests need `libopus` encoding, Opus decoding, and WebM demuxing. Qwen MP3/FLAC/AAC output needs matching encoders.
- Real recognition/synthesis needs compatible upstream services. Tests use local substitutes.

## Nemotron speech recognition

Run from `proxies/`, or adjust the script path:

```bash
python3 speech/nemotron-audio-proxy.py \
  --host 127.0.0.1 \
  --port 8767 \
  --upstream http://127.0.0.1:8766/v1/audio/transcriptions \
  --ffmpeg ffmpeg
```

Command shows all options/defaults. FFmpeg uses `PATH`. Upstream must accept `POST /v1/audio/transcriptions` and return JSON `ready: true` at same-origin `/ready`.

- `GET /ready` and `GET /health` report proxy, FFmpeg, and upstream readiness.
- `POST /audio/transcriptions` and `POST /v1/audio/transcriptions` require `multipart/form-data` with a non-empty `file` part. Optional fields are `model`, `language`, `prompt`, `response_format`, `temperature`, `stream`, and `timestamp_granularities[]`.
- Canonical PCM16 WAV passes unchanged. It must be mono or stereo, 8-96 kHz, at most 600 seconds. FFmpeg converts other supported audio to mono 16 kHz PCM16 WAV.
- Limits are 64 MiB per upload, 25 MiB for WAV passthrough, 600 seconds of converted audio, 90 seconds per conversion, and four concurrent conversions. Upstream wait is at most 600 seconds; responses at most 4 MiB.
- Returns upstream status, content type, and body within the size limit. Connection failure/timeout returns HTTP `502`.

## Qwen3 text-to-speech

Configure with environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `QWEN_TTS_PROXY_HOST` | `127.0.0.1` | Listener interface |
| `QWEN_TTS_PROXY_PORT` | `8769` | Listener port |
| `QWEN_TTS_UPSTREAM_HOST` | `127.0.0.1` | Upstream host |
| `QWEN_TTS_UPSTREAM_PORT` | `8770` | Upstream port |
| `QWEN_TTS_TEMPO` | `1.08` | Fixed FFmpeg `atempo` factor |
| `QWEN_TTS_MAX_BODY` | `1048576` | Maximum JSON request bytes |
| `QWEN_TTS_MAX_SENTENCES` | `12` | Maximum sentence chunks |
| `QWEN_TTS_MAX_TEXT` | `4000` | Maximum input characters |
| `QWEN_TTS_MP3_QUALITY` | `4` | FFmpeg MP3 quality |
| `QWEN_TTS_FFMPEG` | `ffmpeg` | FFmpeg executable or path |

With a separately managed upstream:

```bash
QWEN_TTS_PROXY_HOST=127.0.0.1 \
QWEN_TTS_PROXY_PORT=8769 \
QWEN_TTS_UPSTREAM_HOST=127.0.0.1 \
QWEN_TTS_UPSTREAM_PORT=8770 \
QWEN_TTS_TEMPO=1.08 \
QWEN_TTS_FFMPEG=ffmpeg \
python3 speech/qwen3_tts_tempo_proxy.py
```

- `GET /health` and `/ready` query upstream `GET /health`. `GET /v1/models` lists `qwen3-tts-0.6b-customvoice-q8-gtx` and voice `aiden`. The model identifier preserves API compatibility, not a claim of GPU support.
- `POST /v1/audio/speech` accepts JSON `input` and optional `voice`, `speed`, `response_format`. Each sentence goes to upstream `POST /v1/audio/speech`.
- Upstream must return raw signed 16-bit little-endian PCM, mono, 24 kHz, without a WAV header. The proxy buffers, concatenates, and adjusts tempo, then returns `wav`, `pcm`, `mp3`, `flac`, or `aac`.
- Voices `aiden`, `default`, and `alloy` all use upstream voice `aiden`. `speed` must be `1.0`. Set tempo with `QWEN_TTS_TEMPO`. One process handles synthesis serially, without streaming.
- Body, text, and sentence limits apply. Validation errors return HTTP 400; synthesis or upstream errors return HTTP 500.

## Network safety

Loopback by default. No authentication or TLS. For other hosts, bind to a private interface and restrict access with firewall/VPN isolation. Never expose directly to the internet. Untrusted networks require external authentication and TLS.

## Local test

Run from `proxies/`:

```bash
python3 tools/validate-unified-audio-proxy.py \
  --source-revision <revision-under-test> \
  --evidence "$HOME/proxy-acceptance.json"
```

FFmpeg creates non-speech 440 Hz WAV/WebM/Opus files. Tests run both proxies and local capture services. Checks:

- WAV passthrough without FFmpeg, WebM and incompatible-WAV conversion.
- Normalized audio and request fields at the speech-recognition capture endpoint.
- Response passthrough, malformed-input rejection, and redacted logs.
- Qwen sentence mapping, PCM-to-WAV conversion, and API limits.

JSON records input checksums, tool versions, checks, and limits. No live deployment or real inference contacted. Transcript field is fixed test data, not model output.

Pass proves local proxy behavior only. No speech-quality, model/GPU compatibility, native-build, installation, or security claim beyond loopback isolation. No service restart or public publication.

## Ownership and licenses

Maintainer confirmed ownership and approved inclusion under [Apache-2.0](../LICENSE). Copyright 2026 dpotts34. See [NOTICE](../NOTICE) and [credits](../THIRD_PARTY_NOTICES.md). Private revisions, checksums, and import manifest excluded.

FFmpeg, models, and inference runtimes have separate terms and are not bundled. Inclusion does not authorize deployment or public publication.

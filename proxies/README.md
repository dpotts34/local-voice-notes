# Advanced speech proxy subset

This is a selected, sanitized source subset for advanced evaluation; it is not the supported first-install path. It contains two standalone Python HTTP proxies and one local acceptance harness. No deployment units, model files, service records, archived experiments, operational notes, credentials, or media are included.

## Provenance and redistribution gate

The proxy sources were selected from the maintainer's source tree. Exact private source-revision and file-digest provenance is retained outside this candidate; no private commit identifier or private import manifest is included here. The maintainer confirmed original-project ownership and approved both proxies for inclusion under the root [Apache-2.0 license](../LICENSE), copyright 2026 dpotts34. See [NOTICE](../NOTICE) and [third-party credits](../THIRD_PARTY_NOTICES.md). FFmpeg, models and inference runtimes retain separate terms and are not bundled. Inclusion does not authorize deployment or public publication.

## Runtime requirements

- Python 3.10 or newer; the proxies use only the Python standard library.
- An executable FFmpeg on `PATH` or an explicit executable path.
- Nemotron conversion needs FFmpeg demuxers/decoders for the submitted formats. The acceptance harness additionally needs the `libopus` encoder, an Opus decoder (not necessarily libopus), and a WebM demuxer. Qwen's optional MP3/FLAC/AAC formats need the corresponding FFmpeg encoders.
- A compatible upstream inference service is needed for real ASR/TTS. The offline acceptance harness uses disposable loopback capture stubs instead.

No Python package installation is needed for these files.

## Nemotron audio transcription gateway

Run from this directory or substitute paths to the script:

```bash
python3 speech/nemotron-audio-proxy.py \
  --host 127.0.0.1 \
  --port 8767 \
  --upstream http://127.0.0.1:8766/v1/audio/transcriptions \
  --ffmpeg ffmpeg
```

Options are `--host`, `--port`, `--upstream`, and `--ffmpeg`. Defaults are loopback, port `8767`, a loopback upstream on port `8766`, and `ffmpeg` resolved through `PATH`. The upstream URL must accept `POST /v1/audio/transcriptions`; readiness is queried at the same origin's `/ready` route and expects JSON with `ready: true`.

- `GET /ready` and `GET /health` report proxy, FFmpeg, and upstream readiness.
- `POST /audio/transcriptions` and `POST /v1/audio/transcriptions` accept `multipart/form-data` with a non-empty file part named `file`. Allowed optional fields are `model`, `language`, `prompt`, `response_format`, `temperature`, `stream`, and `timestamp_granularities[]`.
- Canonical PCM16 WAV is forwarded unchanged (mono or stereo, 8–96 kHz, bounded to 600 seconds). Other supported audio is converted by FFmpeg to mono 16 kHz PCM16 WAV before forwarding.
- Uploads are capped at 64 MiB; native WAV passthrough is capped at 25 MiB; conversion is limited to 600 seconds and 90 seconds of wall time, with at most four conversions at once. Upstream wait is capped at 600 seconds and responses at 4 MiB.
- The upstream HTTP status, content type, and body are passed through (subject to the response-size cap); connection/timeout failures become HTTP 502.

The endpoint has no application authentication or TLS. It binds only to loopback by default. To make it reachable from another host, explicitly bind to a private interface and provide firewall/VPN isolation; do not expose it directly to the internet. Add authentication and TLS outside the proxy when the network is not fully trusted.

## Qwen3-TTS sentence/tempo proxy

Configuration is via environment variables:

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
| `QWEN_TTS_MP3_QUALITY` | `4` | FFmpeg MP3 quality setting |
| `QWEN_TTS_FFMPEG` | `ffmpeg` | FFmpeg executable or path |

Example with a separately managed local upstream:

```bash
QWEN_TTS_PROXY_HOST=127.0.0.1 \
QWEN_TTS_PROXY_PORT=8769 \
QWEN_TTS_UPSTREAM_HOST=127.0.0.1 \
QWEN_TTS_UPSTREAM_PORT=8770 \
QWEN_TTS_TEMPO=1.08 \
QWEN_TTS_FFMPEG=ffmpeg \
python3 speech/qwen3_tts_tempo_proxy.py
```

- `GET /health` and `/ready` query upstream `GET /health`; `GET /v1/models` lists the compatibility model identifier `qwen3-tts-0.6b-customvoice-q8-gtx` and voice `aiden`. The suffix is retained for compatibility with the source API; it is not a GPU-support claim.
- `POST /v1/audio/speech` accepts JSON `input`, optional `voice`, `speed`, and `response_format`. Text is split into sentence requests to upstream `POST /v1/audio/speech`. The upstream must return raw signed 16-bit little-endian PCM, mono, at 24 kHz (no WAV header). This fixed representation is buffered, tempo-adjusted, and returned as `wav`, `pcm`, `mp3`, `flac`, or `aac`.
- The accepted voice values are `aiden`, `default`, and `alloy`, but the upstream voice is fixed to `aiden`. `speed` must be `1.0`; tempo is controlled by `QWEN_TTS_TEMPO`. Synthesis is serialized within one process, not streamed, and sentence audio is concatenated.
- Input is capped by body/text/sentence limits above. Validation errors return HTTP 400; synthesis/upstream errors return HTTP 500.

It also has no authentication or TLS and binds to loopback by default. Apply the same private-network restrictions as the Nemotron gateway.

## Disposable acceptance check

From this directory (`proxies/`), run the single local check:

```bash
python3 tools/validate-unified-audio-proxy.py \
  --source-revision <revision-under-test> \
  --evidence "$HOME/proxy-acceptance.json"
```

It generates a synthetic 440 Hz tone (non-speech), derives WAV and WebM/Opus fixtures with FFmpeg, starts both proxies and capture upstreams on loopback, and writes a JSON report to the requested location. It proves WAV passthrough without FFmpeg, WebM and incompatible-WAV conversion, normalized audio and request fields at a disposable ASR capture endpoint, controlled response pass-through, malformed-input rejection, redacted logs, and Qwen sentence mapping plus PCM-to-WAV conversion and API limits. It does not contact a configured deployment or perform ASR/TTS inference; the transcript-like field is a fixed stub response, not a model result. The report records fixture hashes, tool versions, checks, and these limits.

A passing local check is controlled proxy acceptance only. It does not establish real speech quality, upstream model compatibility, GPU support, native builds, a service installation, or deployment security beyond loopback isolation. No service restart or public publication is part of this subset.

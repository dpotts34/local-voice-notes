#!/usr/bin/env python3
"""Local-only acceptance checks for the selected speech proxy subset.

Generates a synthetic, non-speech tone; starts disposable proxy processes and
loopback capture upstreams; and requires real FFmpeg conversions. Nothing
contacts a deployment or performs model inference.

Run from the proxies/ tree:
  python3 tools/validate-unified-audio-proxy.py --evidence /path/outside/tree/report.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from email import policy
from email.parser import BytesParser

STUB_TEXT = "controlled-capture-stub"
STUB_RESPONSE = json.dumps({"text": STUB_TEXT}, separators=(",", ":")).encode()


def fail(message: str) -> None:
    raise AssertionError(message)


def multipart(path: Path, filename: str, content_type: str, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----proxy-validation-" + uuid.uuid4().hex
    chunks: list[bytes] = []

    def add(value: bytes) -> None:
        chunks.append(value)

    for name, value in fields.items():
        add(f"--{boundary}\r\n".encode())
        add(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        add(value.encode())
        add(b"\r\n")
    add(f"--{boundary}\r\n".encode())
    add(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    add(f"Content-Type: {content_type}\r\n\r\n".encode())
    add(path.read_bytes())
    add(b"\r\n")
    add(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def post_audio(url: str, path: Path, filename: str, content_type: str) -> tuple[int, bytes]:
    body, form_type = multipart(
        path,
        filename,
        content_type,
        {"model": "nemotron-speech-streaming-en-0.6b", "response_format": "verbose_json"},
    )
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": form_type, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def post_json(url: str, value: dict[str, object]) -> tuple[int, object, bytes]:
    request = urllib.request.Request(
        url,
        data=json.dumps(value).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def get(url: str, timeout: float = 1.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError:
        return 0, b""


def response_text(status: int, body: bytes, label: str) -> str:
    if status != 200:
        fail(f"{label}: unexpected HTTP {status}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        fail(f"{label}: response is not JSON ({exc})")
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        fail(f"{label}: response has no non-empty string text")
    return text


def wav_info(payload: bytes) -> tuple[int, int, int, int]:
    try:
        with wave.open(io.BytesIO(payload), "rb") as source:
            return source.getnchannels(), source.getframerate(), source.getsampwidth(), source.getnframes()
    except (EOFError, wave.Error) as exc:
        fail(f"payload is not readable WAV ({exc})")


class CaptureHandler(http.server.BaseHTTPRequestHandler):
    server: "CaptureServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ready":
            body = b'{"ready":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        envelope = b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
        message = BytesParser(policy=policy.default).parsebytes(envelope)
        audio = None
        fields: dict[str, str] = {}
        if message.is_multipart():
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                payload = part.get_payload(decode=True) or b""
                if name == "file":
                    audio = payload
                elif name:
                    fields[name] = payload.decode("utf-8", errors="replace")
        if audio is None:
            self.send_error(400)
            return
        record = {
            "method": self.command,
            "path": self.path,
            "audio_sha256": hashlib.sha256(audio).hexdigest(),
            "audio_size": len(audio),
            "fields": fields,
            "wav_info": wav_info(audio),
        }
        with self.server.lock:
            self.server.records.append(record)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(STUB_RESPONSE)))
        self.end_headers()
        self.wfile.write(STUB_RESPONSE)


class CaptureServer(http.server.ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), CaptureHandler)
        self.records: list[dict[str, object]] = []
        self.lock = threading.Lock()


class TTSHandler(http.server.BaseHTTPRequestHandler):
    server: "TTSUpstreamServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(404)
            return
        body = b'{"ready":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400)
            return
        with self.server.lock:
            self.server.records.append({"method": self.command, "path": self.path, "json": value})
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Content-Length", str(len(self.server.pcm)))
        self.end_headers()
        self.wfile.write(self.server.pcm)


class TTSUpstreamServer(http.server.ThreadingHTTPServer):
    def __init__(self, pcm: bytes) -> None:
        super().__init__(("127.0.0.1", 0), TTSHandler)
        self.pcm = pcm
        self.records: list[dict[str, object]] = []
        self.lock = threading.Lock()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for(url: str, process: subprocess.Popen[bytes], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stderr.read().decode(errors="replace") if process.stderr else ""
            fail(f"disposable proxy exited early: {output[-1000:]}")
        status, _ = get(url)
        if status == 200:
            return
        time.sleep(0.1)
    fail("disposable proxy did not become healthy")


def make_wrapper(path: Path, marker: Path, real_ffmpeg: str, fail_on_call: bool) -> None:
    if fail_on_call:
        script = f"#!/bin/sh\nprintf x >> {shlex.quote(str(marker))}\nexit 97\n"
    else:
        script = "#!/bin/sh\n" + f"printf x >> {shlex.quote(str(marker))}\n" + f"exec {shlex.quote(real_ffmpeg)} \"$@\"\n"
    path.write_text(script)
    path.chmod(0o700)


def stop_process(process: subprocess.Popen[bytes]) -> str:
    if process.poll() is None:
        process.terminate()
    try:
        _stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _stdout, stderr = process.communicate(timeout=5)
    return stderr.decode(errors="replace") if stderr else ""


def run_tts_check(ffmpeg: str) -> None:
    pcm = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=24000:duration=0.4", "-ac", "1", "-ar", "24000", "-f", "s16le", "pipe:1"],
        check=True,
        capture_output=True,
        timeout=15,
    ).stdout
    if not pcm:
        fail("FFmpeg did not generate controlled TTS upstream PCM")
    upstream = TTSUpstreamServer(pcm)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    port = free_port()
    env = os.environ.copy()
    env.update({
        "QWEN_TTS_PROXY_HOST": "127.0.0.1",
        "QWEN_TTS_PROXY_PORT": str(port),
        "QWEN_TTS_UPSTREAM_HOST": "127.0.0.1",
        "QWEN_TTS_UPSTREAM_PORT": str(upstream.server_port),
        "QWEN_TTS_TEMPO": "1.08",
        "QWEN_TTS_MAX_BODY": "1048576",
        "QWEN_TTS_MAX_SENTENCES": "12",
        "QWEN_TTS_MAX_TEXT": "4000",
        "QWEN_TTS_MP3_QUALITY": "4",
        "QWEN_TTS_FFMPEG": ffmpeg,
    })
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "speech/qwen3_tts_tempo_proxy.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        wait_for(base + "/ready", process)
        health_status, health_body = get(base + "/ready")
        health = json.loads(health_body)
        if health_status != 200 or health.get("ready") is not True:
            fail("Qwen proxy did not report a healthy controlled upstream")
        model_status, model_body = get(base + "/v1/models")
        model_data = json.loads(model_body)
        if model_status != 200 or model_data.get("object") != "list" or not model_data.get("data"):
            fail("Qwen /v1/models response contract failed")

        status, headers, body = post_json(base + "/v1/audio/speech", {
            "input": "First sample. Second sample.",
            "voice": "aiden",
            "response_format": "wav",
        })
        if status != 200 or headers.get("Content-Type") != "audio/wav":
            fail("Qwen proxy did not return a WAV response")
        if headers.get("X-Qwen-TTS-Chunks") != "2" or headers.get("X-Qwen-TTS-Tempo") != "1.08":
            fail("Qwen proxy did not preserve chunk/tempo response headers")
        channels, rate, width, frames = wav_info(body)
        if (channels, rate, width) != (1, 24000, 2) or frames <= 0:
            fail("Qwen FFmpeg output was not non-empty mono 24 kHz PCM16 WAV")
        expected_fields = {
            "voice": "aiden",
            "response_format": "pcm",
            "temperature": 0,
            "top_k": 0,
            "seed": 42,
            "max_new_tokens": 256,
        }
        with upstream.lock:
            records = list(upstream.records)
        if len(records) != 2 or [item["path"] for item in records] != ["/v1/audio/speech"] * 2:
            fail("Qwen proxy did not make one upstream POST for each sentence")
        for record, sentence in zip(records, ("First sample.", "Second sample."), strict=True):
            forwarded = record["json"]
            if record["method"] != "POST" or forwarded != {"input": sentence, **expected_fields}:
                fail("Qwen upstream request fields did not match the controlled API contract")

        too_many = ". ".join(f"Sentence {index}" for index in range(13)) + "."
        status, _headers, error_body = post_json(base + "/v1/audio/speech", {"input": too_many})
        if status != 400 or len(upstream.records) != 2:
            fail("Qwen sentence limit did not reject before upstream")
        if "invalid_request_error" not in error_body.decode(errors="replace"):
            fail("Qwen sentence-limit response was not an API error")
        print("PASS qwen-tts: health/models, sentence mapping, controlled upstream PCM, FFmpeg WAV output, and sentence limit")
    finally:
        logs = stop_process(process)
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)
        if "Traceback" in logs:
            fail("Qwen proxy logged an uncontrolled exception")


def run_local(args: argparse.Namespace) -> None:
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg or (not shutil.which(ffmpeg) and not Path(ffmpeg).is_file()):
        fail("an executable FFmpeg is required")

    evidence_checks = [
        "native WAV passthrough without FFmpeg",
        "WebM/Opus conversion to mono 16 kHz PCM16 WAV",
        "incompatible WAV conversion to mono 16 kHz PCM16 WAV",
        "malformed WAV bounded rejection without forwarding or path disclosure",
        "Qwen sentence mapping and controlled upstream PCM to FFmpeg WAV output",
    ]
    with tempfile.TemporaryDirectory(prefix="proxy-validation-") as temp:
        root = Path(temp)
        wav = root / "synthetic-tone.wav"
        webm = root / "synthetic-tone.webm"
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.5", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
            check=True,
            timeout=15,
        )
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", "-b:a", "32k", "-vn", str(webm)],
            check=True,
            timeout=15,
        )
        unsupported = root / "unsupported.wav"
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav), "-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le", str(unsupported)],
            check=True,
            timeout=15,
        )
        marker = root / "ffmpeg-called"
        sentinel = root / "ffmpeg-sentinel"
        wrapper = root / "ffmpeg-wrapper"
        make_wrapper(sentinel, marker, ffmpeg, fail_on_call=True)
        make_wrapper(wrapper, marker, ffmpeg, fail_on_call=False)

        capture = CaptureServer()
        capture_thread = threading.Thread(target=capture.serve_forever, daemon=True)
        capture_thread.start()
        upstream_url = f"http://127.0.0.1:{capture.server_port}/v1/audio/transcriptions"
        proxy_port = free_port()
        command = [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "speech/nemotron-audio-proxy.py"),
            "--host", "127.0.0.1",
            "--port", str(proxy_port),
            "--upstream", upstream_url,
            "--ffmpeg", str(sentinel),
        ]
        proxy = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        base = f"http://127.0.0.1:{proxy_port}"
        first_logs = ""
        try:
            wait_for(base + "/health", proxy)
            health_status, health_body = get(base + "/health")
            health = json.loads(health_body)
            if health_status != 200 or health.get("ready") is not True or health.get("upstream", {}).get("ready") is not True:
                fail("Nemotron health did not confirm the controlled upstream")

            status, body = post_audio(base + "/v1/audio/transcriptions", wav, "native-secret.wav", "audio/wav")
            if response_text(status, body, "native WAV") != STUB_TEXT or body != STUB_RESPONSE:
                fail("Nemotron did not pass through the controlled upstream response")
            if marker.exists():
                fail("native WAV invoked FFmpeg")
            with capture.lock:
                if len(capture.records) != 1:
                    fail("native WAV did not produce exactly one upstream request")
                native = capture.records[-1]
            if native["method"] != "POST" or native["path"] != "/v1/audio/transcriptions":
                fail("native WAV upstream method or route changed")
            if native["fields"] != {"model": "nemotron-speech-streaming-en-0.6b", "response_format": "verbose_json"}:
                fail("native WAV upstream form fields changed")
            if native["audio_sha256"] != hashlib.sha256(wav.read_bytes()).hexdigest() or native["wav_info"] != wav_info(wav.read_bytes()):
                fail("native WAV was not forwarded byte-for-byte")

            first_logs = stop_process(proxy)
            proxy = subprocess.Popen([*command[:-1], str(wrapper)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            wait_for(base + "/health", proxy)
            status, body = post_audio(base + "/v1/audio/transcriptions", webm, "compressed-secret.webm", "audio/webm")
            if response_text(status, body, "WebM") != STUB_TEXT or body != STUB_RESPONSE:
                fail("WebM conversion did not return the controlled upstream response")
            if not marker.exists() or marker.stat().st_size != 1:
                fail("WebM did not invoke FFmpeg exactly once")
            with capture.lock:
                if len(capture.records) != 2:
                    fail("WebM did not produce exactly one additional upstream request")
                webm_record = capture.records[-1]
            if webm_record["audio_sha256"] == hashlib.sha256(webm.read_bytes()).hexdigest():
                fail("WebM bytes were forwarded unchanged")
            if webm_record["wav_info"][:3] != (1, 16000, 2) or webm_record["wav_info"][3] <= 0:
                fail("converted WebM was not non-empty mono 16 kHz PCM16 WAV")

            marker_size = marker.stat().st_size
            status, body = post_audio(base + "/v1/audio/transcriptions", unsupported, "unsupported-secret.wav", "audio/wav")
            if response_text(status, body, "unsupported WAV") != STUB_TEXT or marker.stat().st_size <= marker_size:
                fail("incompatible WAV did not convert and reach the controlled upstream")
            with capture.lock:
                if len(capture.records) != 3 or capture.records[-1]["wav_info"][:3] != (1, 16000, 2):
                    fail("incompatible WAV was not normalized at the upstream boundary")

            malformed = root / "malformed.wav"
            malformed.write_bytes(b"RIFF\\x10\\x00\\x00\\x00WAVEfmt ")
            before_records = len(capture.records)
            before_marker = marker.stat().st_size
            status, body = post_audio(base + "/v1/audio/transcriptions", malformed, "malformed-secret.wav", "audio/wav")
            if status not in {400, 422} or len(capture.records) != before_records:
                fail(f"malformed WAV was not rejected before upstream (HTTP {status})")
            if marker.stat().st_size <= before_marker or any(token in body.decode(errors="replace") for token in ("Traceback", "proxy-validation-", "/tmp/")):
                fail("malformed WAV conversion did not fail safely or disclosed an internal path")

            logs = first_logs + stop_process(proxy)
            for label in ("Passing native PCM16 WAV through without conversion", "Converting audio upload to PCM16 WAV"):
                if label not in logs:
                    fail(f"Nemotron logs lack branch evidence: {label}")
            for secret in ("native-secret.wav", "compressed-secret.webm", "unsupported-secret.wav", "malformed-secret.wav", "proxy-validation-"):
                if secret in logs:
                    fail("Nemotron logs disclosed an upload filename or temporary path")
            if "Unexpected proxy failure" in logs or "Traceback" in logs:
                fail("Nemotron logged an uncontrolled exception")
            print("PASS nemotron: health, request/response forwarding, passthrough, WebM conversion, incompatible WAV conversion, malformed-input rejection, redacted logs")
        finally:
            stop_process(proxy)
            capture.shutdown()
            capture.server_close()
            capture_thread.join(timeout=5)

        run_tts_check(ffmpeg)
        if args.evidence:
            version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
            report = {
                "result": "PASS",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source_revision": args.source_revision,
                "runtime": {"python": sys.version.split()[0], "ffmpeg": version},
                "network_scope": "loopback-only disposable proxy and capture upstreams",
                "fixture": {
                    "kind": "synthetic 440 Hz tone; non-speech and not an inference fixture",
                    "wav_bytes": wav.stat().st_size,
                    "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                    "webm_bytes": webm.stat().st_size,
                    "webm_sha256": hashlib.sha256(webm.read_bytes()).hexdigest(),
                },
                "checks": [{"name": item, "result": "PASS"} for item in evidence_checks],
                "limits": [
                    "Capture upstreams return controlled responses; no ASR/TTS model inference was performed.",
                    "No GPU runtime, hardware compatibility, native build, deployment service, or production network was tested.",
                ],
            }
            evidence = Path(args.evidence).expanduser().resolve()
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Evidence: {evidence}")
        print("PASS disposable speech proxy acceptance (controlled stubs; no inference)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ffmpeg", default=None, help="FFmpeg executable (default: found on PATH)")
    parser.add_argument("--evidence", help="optional JSON report path outside the selected source tree")
    parser.add_argument("--source-revision", default="unspecified", help="source revision recorded in the evidence report")
    return parser.parse_args()


def main() -> int:
    run_local(parse_args())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)

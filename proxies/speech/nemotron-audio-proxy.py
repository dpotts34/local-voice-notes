#!/usr/bin/env python3
"""Unified OpenAI-compatible audio-file gateway for NeMo-Speech.cpp.

Accepts multipart audio uploads from clients such as OpenWhispr, passes native
PCM16 WAV through unchanged, converts other input to mono 16 kHz signed 16-bit
WAV, and forwards it to the Nemotron server. Uses only the Python standard
library plus an ffmpeg executable.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import signal
import shutil
import struct
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

LOG = logging.getLogger("nemotron-audio-proxy")
ALLOWED_POST_PATHS = {"/audio/transcriptions", "/v1/audio/transcriptions"}
ALLOWED_FIELDS = {
    "model",
    "language",
    "prompt",
    "response_format",
    "temperature",
    "stream",
    "timestamp_granularities[]",
}
MAX_FIELD_BYTES = 16 * 1024
MAX_FIELD_TOTAL = 256 * 1024
MAX_PARTS = 32
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_WAV_BYTES = 25 * 1024 * 1024
CONVERSION_SLOTS = threading.BoundedSemaphore(4)


class ProxyConfig:
    host = "127.0.0.1"
    port = 8767
    upstream = "http://127.0.0.1:8766/v1/audio/transcriptions"
    upstream_ready = "http://127.0.0.1:8766/ready"
    ffmpeg = "ffmpeg"
    max_upload = 64 * 1024 * 1024
    max_duration = 600
    convert_timeout = 90
    upstream_timeout = 600


def json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def error_payload(status: int, message: str, code: str) -> bytes:
    return json_bytes(
        {
            "error": {
                "code": code,
                "message": message,
                "param": None,
                "type": "invalid_request_error" if status < 500 else "server_error",
            }
        }
    )


def parse_multipart(content_type: str, body: bytes) -> tuple[bytes, str, list[tuple[str, str]]]:
    if "\r" in content_type or "\n" in content_type:
        raise ValueError("invalid Content-Type header")
    if not content_type.lower().startswith("multipart/form-data;"):
        raise ValueError("Content-Type must be multipart/form-data")

    envelope = (
        b"Content-Type: "
        + content_type.encode("latin-1")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    message = BytesParser(policy=policy.default).parsebytes(envelope)
    if not message.is_multipart():
        raise ValueError("invalid multipart body")

    audio: bytes | None = None
    filename = "audio.bin"
    fields: list[tuple[str, str]] = []
    parts = list(message.iter_parts())
    if len(parts) > MAX_PARTS:
        raise ValueError("multipart request has too many parts")
    field_total = 0
    for part in parts:
        if part.is_multipart():
            raise ValueError("nested multipart parts are not allowed")
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        part_filename = part.get_filename()
        if name == "file" and part_filename is not None:
            if audio is not None:
                raise ValueError("only one audio file is allowed")
            if not payload:
                raise ValueError("audio file is empty")
            audio = payload
            filename = Path(part_filename).name or "audio.bin"
        elif name in ALLOWED_FIELDS:
            if len(payload) > MAX_FIELD_BYTES:
                raise ValueError(f"form field {name!r} is too large")
            field_total += len(payload)
            if field_total > MAX_FIELD_TOTAL:
                raise ValueError("multipart form fields are too large")
            fields.append((name, payload.decode("utf-8", errors="replace")))

    if audio is None:
        raise ValueError("multipart field 'file' is required")
    return audio, filename, fields


def multipart_body(wav: bytes, fields: Iterable[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----nemotron-proxy-" + secrets.token_hex(16)
    chunks: list[bytes] = []

    def add(value: bytes) -> None:
        chunks.append(value)

    for name, value in fields:
        safe_name = name.replace('"', "")
        add(f"--{boundary}\r\n".encode())
        add(f'Content-Disposition: form-data; name="{safe_name}"\r\n\r\n'.encode())
        add(value.encode("utf-8"))
        add(b"\r\n")

    add(f"--{boundary}\r\n".encode())
    add(b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n')
    add(b"Content-Type: audio/wav\r\n\r\n")
    add(wav)
    add(b"\r\n")
    add(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def is_native_pcm16_wav(audio: bytes) -> bool:
    """Strictly recognize bounded canonical PCM16 WAV for safe passthrough."""
    if (
        len(audio) < 44
        or len(audio) > MAX_WAV_BYTES
        or audio[:4] != b"RIFF"
        or audio[8:12] != b"WAVE"
    ):
        return False
    try:
        riff_size = struct.unpack_from("<I", audio, 4)[0]
        if riff_size + 8 != len(audio):
            return False

        fmt: tuple[int, int, int, int, int, int] | None = None
        data_size: int | None = None
        offset = 12
        while offset < len(audio):
            if offset + 8 > len(audio):
                return False
            chunk_id = audio[offset : offset + 4]
            chunk_size = struct.unpack_from("<I", audio, offset + 4)[0]
            payload_start = offset + 8
            payload_end = payload_start + chunk_size
            padded_end = payload_end + (chunk_size & 1)
            if payload_end > len(audio) or padded_end > len(audio):
                return False

            if chunk_id == b"fmt ":
                if fmt is not None or chunk_size != 16:
                    return False
                fmt = struct.unpack_from("<HHIIHH", audio, payload_start)
            elif chunk_id == b"data":
                if data_size is not None:
                    return False
                data_size = chunk_size
            offset = padded_end

        if offset != len(audio) or fmt is None or data_size is None:
            return False
        format_tag, channels, rate, byte_rate, block_align, bits = fmt
        expected_align = channels * 2
        if (
            format_tag != 1
            or bits != 16
            or channels not in {1, 2}
            or not 8000 <= rate <= 96000
            or block_align != expected_align
            or byte_rate != rate * expected_align
            or data_size <= 0
            or data_size % expected_align != 0
        ):
            return False
        frames = data_size // expected_align
        return frames <= ProxyConfig.max_duration * rate
    except (struct.error, OverflowError):
        return False


def convert_audio(audio: bytes, filename: str) -> bytes:
    suffix = Path(filename).suffix.lower()
    if not suffix or len(suffix) > 10 or not suffix[1:].isalnum():
        suffix = ".bin"
    with tempfile.TemporaryDirectory(prefix="nemotron-audio-") as temp_dir:
        input_path = Path(temp_dir) / ("input" + suffix)
        output_path = Path(temp_dir) / "output.wav"
        input_path.write_bytes(audio)
        command = [
            ProxyConfig.ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(input_path),
            "-map",
            "0:a:0",
            "-map_metadata",
            "-1",
            "-t",
            str(ProxyConfig.max_duration),
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-fs",
            str(MAX_WAV_BYTES),
            str(output_path),
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            _, stderr = process.communicate(timeout=ProxyConfig.convert_timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            _, stderr = process.communicate()
            raise ValueError("audio conversion timed out") from exc
        if process.returncode != 0 or not output_path.is_file():
            LOG.warning("FFmpeg rejected an audio upload")
            raise ValueError("unsupported or invalid audio")
        try:
            with wave.open(str(output_path), "rb") as wav_file:
                valid_wav = (
                    wav_file.getnchannels() == 1
                    and wav_file.getframerate() == 16000
                    and wav_file.getsampwidth() == 2
                    and 0 < wav_file.getnframes() <= ProxyConfig.max_duration * 16000
                )
        except (wave.Error, EOFError):
            valid_wav = False
        if not valid_wav:
            raise ValueError("audio conversion produced an invalid WAV file")
        wav = output_path.read_bytes()
        if len(wav) <= 44 or len(wav) > MAX_WAV_BYTES:
            raise ValueError("audio conversion produced no samples")
        return wav


def forward(wav: bytes, fields: list[tuple[str, str]]) -> tuple[int, str, bytes]:
    if not any(name == "model" for name, _ in fields):
        fields.append(("model", "nemotron-speech-streaming-en-0.6b"))
    body, content_type = multipart_body(wav, fields)
    request = urllib.request.Request(
        ProxyConfig.upstream,
        data=body,
        method="POST",
        headers={"Content-Type": content_type, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=ProxyConfig.upstream_timeout) as response:
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(response_body) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Nemotron response exceeded the size limit")
            return response.status, response.headers.get("Content-Type", "application/json"), response_body
    except urllib.error.HTTPError as exc:
        response_body = exc.read(MAX_RESPONSE_BYTES + 1)
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Nemotron error response exceeded the size limit")
        return exc.code, exc.headers.get("Content-Type", "application/json"), response_body
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Nemotron upstream is unavailable: {exc.reason if hasattr(exc, 'reason') else exc}") from exc


class Handler(BaseHTTPRequestHandler):
    server_version = "AudioProxy"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt: str, *args: object) -> None:
        LOG.info("%s - %s", self.client_address[0], fmt % args)

    def send_body(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in {"/ready", "/health"}:
            self.send_body(HTTPStatus.NOT_FOUND, error_payload(404, "route not found", "not_found"))
            return
        try:
            with urllib.request.urlopen(ProxyConfig.upstream_ready, timeout=3) as response:
                upstream = json.loads(response.read().decode("utf-8"))
            ffmpeg_ok = os.path.isfile(ProxyConfig.ffmpeg) and os.access(ProxyConfig.ffmpeg, os.X_OK)
            ready = response.status == 200 and bool(upstream.get("ready")) and ffmpeg_ok
            self.send_body(200 if ready else 503, json_bytes({"ready": ready, "proxy": True, "ffmpeg": ffmpeg_ok, "upstream": upstream}))
        except Exception as exc:
            self.send_body(503, json_bytes({"ready": False, "proxy": True, "error": str(exc)}))

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in ALLOWED_POST_PATHS:
            self.send_body(HTTPStatus.NOT_FOUND, error_payload(404, "route not found", "not_found"))
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                self.send_body(400, error_payload(400, "Transfer-Encoding is not supported", "invalid_transfer_encoding"))
                return
            content_encoding = self.headers.get("Content-Encoding", "identity").strip().lower()
            if content_encoding not in {"", "identity"}:
                self.send_body(400, error_payload(400, "Content-Encoding is not supported", "invalid_content_encoding"))
                return
            length_headers = self.headers.get_all("Content-Length", [])
            if not length_headers:
                self.send_body(411, error_payload(411, "Content-Length is required", "length_required"))
                return
            if len(length_headers) != 1 or "," in length_headers[0]:
                self.send_body(400, error_payload(400, "exactly one Content-Length is required", "invalid_length"))
                return
            raw_length = length_headers[0]
            try:
                length = int(raw_length)
            except ValueError:
                self.send_body(400, error_payload(400, "invalid Content-Length", "invalid_length"))
                return
            if length <= 0 or length > ProxyConfig.max_upload:
                self.send_body(413, error_payload(413, "audio request is too large", "request_too_large"))
                return
            chunks: list[bytes] = []
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            if remaining:
                self.send_body(400, error_payload(400, "incomplete request body", "incomplete_body"))
                return
            body = b"".join(chunks)
            audio, filename, fields = parse_multipart(self.headers.get("Content-Type", ""), body)
            if not CONVERSION_SLOTS.acquire(timeout=15):
                self.send_body(503, error_payload(503, "conversion service is busy", "service_busy"))
                return
            try:
                if is_native_pcm16_wav(audio):
                    LOG.info("Passing native PCM16 WAV through without conversion (%d bytes)", len(audio))
                    wav = audio
                else:
                    LOG.info("Converting audio upload to PCM16 WAV (%d bytes)", len(audio))
                    wav = convert_audio(audio, filename)
                LOG.info("Forwarding WAV (%d bytes) to Nemotron", len(wav))
                status, content_type, upstream_body = forward(wav, fields)
            finally:
                CONVERSION_SLOTS.release()
            self.send_body(status, upstream_body, content_type)
        except ValueError as exc:
            LOG.warning("Rejected request: %s", exc)
            self.send_body(400, error_payload(400, str(exc), "invalid_audio"))
        except RuntimeError as exc:
            LOG.error("Upstream error: %s", exc)
            self.send_body(502, error_payload(502, str(exc), "upstream_unavailable"))
        except Exception:
            LOG.exception("Unexpected proxy failure")
            self.send_body(500, error_payload(500, "internal conversion proxy error", "proxy_error"))


class ProxyServer(ThreadingHTTPServer):
    request_queue_size = 32


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=ProxyConfig.host)
    parser.add_argument("--port", type=int, default=ProxyConfig.port)
    parser.add_argument("--upstream", default=ProxyConfig.upstream)
    parser.add_argument("--ffmpeg", default=ProxyConfig.ffmpeg)
    args = parser.parse_args()
    ProxyConfig.host = args.host
    ProxyConfig.port = args.port
    ProxyConfig.upstream = args.upstream
    parsed_upstream = urllib.parse.urlsplit(args.upstream)
    ProxyConfig.upstream_ready = urllib.parse.urlunsplit(
        (parsed_upstream.scheme, parsed_upstream.netloc, "/ready", "", "")
    )
    ProxyConfig.ffmpeg = args.ffmpeg
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    resolved_ffmpeg = shutil.which(ProxyConfig.ffmpeg)
    if not resolved_ffmpeg:
        raise SystemExit(f"ffmpeg is not executable: {ProxyConfig.ffmpeg}")
    ProxyConfig.ffmpeg = resolved_ffmpeg
    server = ProxyServer((ProxyConfig.host, ProxyConfig.port), Handler)
    server.daemon_threads = True
    LOG.info("Listening on http://%s:%d; upstream=%s", ProxyConfig.host, ProxyConfig.port, ProxyConfig.upstream)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

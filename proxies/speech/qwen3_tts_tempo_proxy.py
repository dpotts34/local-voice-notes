#!/usr/bin/env python3
"""LAN OpenAI-compatible proxy for GPU Qwen3-TTS with sentence chunking and tempo DSP."""

from __future__ import annotations

import http.client
import json
import logging
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.getenv("QWEN_TTS_PROXY_HOST", "127.0.0.1")
PORT = int(os.getenv("QWEN_TTS_PROXY_PORT", "8769"))
UPSTREAM_HOST = os.getenv("QWEN_TTS_UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.getenv("QWEN_TTS_UPSTREAM_PORT", "8770"))
TEMPO = float(os.getenv("QWEN_TTS_TEMPO", "1.08"))
MAX_BODY = int(os.getenv("QWEN_TTS_MAX_BODY", "1048576"))
MAX_SENTENCES = int(os.getenv("QWEN_TTS_MAX_SENTENCES", "12"))
MAX_TEXT = int(os.getenv("QWEN_TTS_MAX_TEXT", "4000"))
ALLOWED_VOICE = "aiden"
FFMPEG = os.getenv("QWEN_TTS_FFMPEG", "ffmpeg")
SYNTHESIS_LOCK = threading.Lock()
LOG = logging.getLogger("qwen3-tts-proxy")


def split_sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if len(parts) > MAX_SENTENCES:
        raise ValueError(f"input exceeds {MAX_SENTENCES} sentence chunks")
    return parts


def upstream_pcm(sentence: str):
    payload = json.dumps(
        {
            "input": sentence,
            "voice": ALLOWED_VOICE,
            "response_format": "pcm",
            "temperature": 0,
            "top_k": 0,
            "seed": 42,
            "max_new_tokens": 256,
        }
    ).encode()
    conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=180)
    conn.request(
        "POST",
        "/v1/audio/speech",
        body=payload,
        headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
    )
    response = conn.getresponse()
    if response.status != 200:
        error = response.read().decode(errors="replace")
        conn.close()
        raise RuntimeError(f"upstream HTTP {response.status}: {error}")
    return conn, response


def ffmpeg_command(output_format: str) -> list[str]:
    command = [
        FFMPEG,
        "-v",
        "error",
        "-f",
        "s16le",
        "-ar",
        "24000",
        "-ac",
        "1",
        "-i",
        "pipe:0",
        "-filter:a",
        f"atempo={TEMPO:.8f}",
    ]
    if output_format == "pcm":
        return command + ["-f", "s16le", "pipe:1"]
    if output_format == "mp3":
        quality = os.getenv("QWEN_TTS_MP3_QUALITY", "4")
        return command + ["-f", "mp3", "-q:a", quality, "pipe:1"]
    if output_format == "flac":
        return command + ["-f", "flac", "-c:a", "flac", "pipe:1"]
    if output_format == "aac":
        return command + ["-f", "adts", "-c:a", "aac", "-b:a", "128k", "pipe:1"]
    return command + ["-f", "wav", "-c:a", "pcm_s16le", "pipe:1"]


def synthesize_buffered(sentences: list[str], output_format: str) -> bytes:
    pcm = bytearray()
    for sentence in sentences:
        conn, response = upstream_pcm(sentence)
        try:
            while chunk := response.read1(65536):
                pcm.extend(chunk)
        finally:
            response.close()
            conn.close()
    result = subprocess.run(
        ffmpeg_command(output_format),
        input=bytes(pcm),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr.decode(errors='replace')}")
    return result.stdout


class Handler(BaseHTTPRequestHandler):
    server_version = "Qwen3TTSProxy/1.0"

    def log_message(self, fmt: str, *args) -> None:
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def send_json(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path in ("/health", "/ready"):
            try:
                conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=2)
                conn.request("GET", "/health")
                response = conn.getresponse()
                ready = response.status == 200
                response.read()
                conn.close()
            except Exception:
                ready = False
            self.send_json(200 if ready else 503, {"ready": ready, "upstream": ready, "tempo": TEMPO})
            return
        if self.path == "/v1/models":
            self.send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "qwen3-tts-0.6b-customvoice-q8-gtx",
                            "object": "model",
                            "owned_by": "local",
                            "voices": [ALLOWED_VOICE],
                            "speed": TEMPO,
                        }
                    ],
                },
            )
            return
        self.send_json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        if self.path != "/v1/audio/speech":
            self.send_json(404, {"error": {"message": "not found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": {"message": "invalid Content-Length"}})
            return
        if length <= 0 or length > MAX_BODY:
            self.send_json(413 if length > MAX_BODY else 400, {"error": {"message": "invalid body size"}})
            return
        try:
            request = json.loads(self.rfile.read(length))
            text = request.get("input", "")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("input must be a non-empty string")
            if len(text) > MAX_TEXT:
                raise ValueError(f"input exceeds {MAX_TEXT} characters")
            voice = request.get("voice", ALLOWED_VOICE)
            if voice not in (ALLOWED_VOICE, "default", "alloy"):
                raise ValueError(f"only voice '{ALLOWED_VOICE}' is validated")
            speed = float(request.get("speed", 1.0))
            if speed != 1.0:
                raise ValueError("speed is fixed by the deployed voice profile")
            output_format = request.get("response_format", "wav")
            if output_format not in ("wav", "pcm", "mp3", "flac", "aac"):
                raise ValueError("response_format must be wav, pcm, mp3, flac, or aac")
            sentences = split_sentences(text)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": {"message": str(error), "type": "invalid_request_error"}})
            return

        with SYNTHESIS_LOCK:
            try:
                # WAV is buffered so its RIFF sizes are valid. PCM remains suitable
                # for the later realtime bridge, which can consume native chunks.
                audio = synthesize_buffered(sentences, output_format)
                self.send_response(200)
                content_types = {"wav": "audio/wav", "pcm": "audio/pcm", "mp3": "audio/mpeg", "flac": "audio/flac", "aac": "audio/aac"}
                self.send_header("Content-Type", content_types[output_format])
                self.send_header("Content-Length", str(len(audio)))
                self.send_header("X-Qwen-TTS-Tempo", f"{TEMPO:.2f}")
                self.send_header("X-Qwen-TTS-Chunks", str(len(sentences)))
                self.end_headers()
                self.wfile.write(audio)
            except Exception as error:
                LOG.exception("synthesis failed")
                self.send_json(500, {"error": {"message": str(error), "type": "server_error"}})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    LOG.info("listening on %s:%d -> %s:%d tempo=%.2f", HOST, PORT, UPSTREAM_HOST, UPSTREAM_PORT, TEMPO)
    server.serve_forever()

from __future__ import annotations

import json
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath

import aiohttp

from .config import Config
from .note_action import InvalidNoteAction, NoteAction, parse_note_action

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
}

SYSTEM_PROMPT = (
    "Return only one JSON object with exactly title, body, tags, summary. "
    "title/body/summary are non-empty strings and tags is an array of strings. "
    "Use a short readable title without a date or request ID. "
    "Tags must be unique, contain no whitespace, underscore or leading #, and not be numeric-only. "
    "Separate tag words with hyphens; preserve / for nested tags. "
    "Do not skip heading levels in the body; the note already has an H1 title. "
    "Do not return a path, operation, markdown fence, or extra fields."
)


class ExternalClients:
    def __init__(self, config: Config):
        self.config = config
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "ExternalClients":
        timeout = aiohttp.ClientTimeout(total=self.config.http_timeout_seconds, connect=min(5, self.config.http_timeout_seconds))
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            raise RuntimeError("client is not open")
        return self.session

    async def transcribe(
        self, audio_path: Path, content_type: str, expected_sha256: str, expected_bytes: int
    ) -> str:
        fd = os.open(audio_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise OSError("ASR input is not a regular file")
            digest = hashlib.sha256()
            size = 0
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
            if size != expected_bytes or digest.hexdigest() != expected_sha256:
                raise OSError("ASR input integrity conflict")
            source.seek(0)
            form = aiohttp.FormData()
            form.add_field("file", source, filename=audio_path.name, content_type=content_type)
            async with self._session().post(self.config.asr_url, data=form) as response:
                response.raise_for_status()
                payload = await response.json()
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError("ASR returned no transcript")
        return text.strip()

    async def format_note(self, transcript: str) -> NoteAction:
        targets = [(self.config.llm_url, self.config.llm_model)]
        if self.config.llm_fallback_url and self.config.llm_fallback_model:
            targets.append((self.config.llm_fallback_url, self.config.llm_fallback_model))
        last_error: Exception | None = None
        for target_index, (url, model) in enumerate(targets):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Format this transcript:\n{transcript}"},
            ]
            try:
                for attempt in range(2):
                    payload = {
                        "model": model,
                        "messages": messages,
                        "response_format": {"type": "json_schema", "schema": NOTE_SCHEMA},
                        "temperature": 0,
                        "chat_template_kwargs": {"enable_thinking": False},
                    }
                    timeout_seconds = (
                        self.config.llm_primary_timeout_seconds if target_index == 0
                        else self.config.llm_fallback_timeout_seconds
                    )
                    async with self._session().post(
                        url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout_seconds)
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
                    try:
                        content = data["choices"][0]["message"]["content"]
                        if not isinstance(content, str):
                            raise InvalidNoteAction("LLM content is not text")
                        return parse_note_action(content)
                    except (KeyError, IndexError, TypeError, InvalidNoteAction) as error:
                        last_error = error if isinstance(error, InvalidNoteAction) else InvalidNoteAction("invalid LLM response envelope")
                        if attempt == 0:
                            messages.append({
                                "role": "user",
                                "content": "Repair your response. Return only exactly title, body, tags, summary with the required types; no extra fields.",
                            })
                raise last_error or InvalidNoteAction("invalid model response")
            except Exception as error:
                last_error = error
        raise last_error or InvalidNoteAction("invalid model response")

    async def notify(
        self, status: str, note_path: str | None, request_id: str, thread_id: str,
        notification_nonce: str, summary: str | None = None,
    ) -> str | None:
        if note_path is not None:
            path = PurePosixPath(note_path)
            inbox = PurePosixPath(self.config.inbox.as_posix())
            if path.is_absolute() or ".." in path.parts or path.parts[: len(inbox.parts)] != inbox.parts:
                raise ValueError("unsafe note path")
        titles = {"completed": "Voice note completed", "failed": "Voice note failed"}
        tags = {"completed": "white_check_mark,memo", "failed": "warning,memo"}
        priorities = {"completed": "default", "failed": "high"}
        lines = [status.capitalize() + " voice note"]
        if note_path is not None:
            lines.append(f"Note: {note_path}")
        if summary is not None:
            lines.append(f"Summary: {summary}")
        lines.extend((f"Request: {request_id}", f"Thread: {thread_id}"))
        title = titles.get(status, "Voice note update")
        message = "\n".join(lines)
        identity = "vni-" + hashlib.sha256(
            f"voice-note-intake\0{notification_nonce}\0{status}\0{request_id}".encode()
        ).hexdigest()
        history_url = self.config.ntfy_url.rstrip("/") + "/json"
        async with self._session().get(history_url, params={"poll": "1", "since": "all"}) as response:
            if response.status not in {404, 405}:
                response.raise_for_status()
                for line in (await response.text()).splitlines():
                    try:
                        cached = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (
                        isinstance(cached, dict)
                        and cached.get("event") == "message"
                        and isinstance(cached.get("tags"), list)
                        and identity in cached["tags"]
                        and isinstance(cached.get("id"), str)
                        and cached["id"].strip()
                        and cached.get("title") == title
                        and cached.get("message") == message
                    ):
                        return cached["id"].strip()
        headers = {
            "Title": title,
            "Tags": f"{tags.get(status, 'memo')},{identity}",
            "Priority": priorities.get(status, "default"),
            "Content-Type": "text/plain; charset=utf-8",
        }
        async with self._session().post(self.config.ntfy_url, data=message.encode(), headers=headers) as response:
            response.raise_for_status()
            raw = await response.text()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("ntfy returned no valid event ID") from None
        event_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("ntfy returned no valid event ID")
        return event_id.strip()

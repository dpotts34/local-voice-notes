from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass


class InvalidNoteAction(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NoteAction:
    title: str
    body: str
    tags: tuple[str, ...]
    summary: str


def tag_error(tag: str) -> str | None:
    if not tag or any(not part for part in tag.split("/")):
        return "empty tag or hierarchy segment"
    if tag.isnumeric():
        return "numeric-only tag"
    if any(c not in "-/" and unicodedata.category(c)[0] not in "LNMS" for c in tag):
        return "use hyphens between words; no whitespace, underscore, or # prefix"
    return None


def parse_note_action(content: str) -> NoteAction:
    def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        if len(pairs) != len({key for key, _ in pairs}):
            raise InvalidNoteAction("model response has duplicate fields")
        return dict(pairs)

    text = content.strip()
    try:
        value = json.loads(text, object_pairs_hook=strict_object)
    except json.JSONDecodeError as error:
        raise InvalidNoteAction("model response is not exactly one JSON object") from error
    if not isinstance(value, dict) or set(value) != {"title", "body", "tags", "summary"}:
        raise InvalidNoteAction("model response has unexpected fields")
    title, body, tags, summary = (value[key] for key in ("title", "body", "tags", "summary"))
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise InvalidNoteAction("invalid title")
    if not isinstance(body, str) or not body.strip() or len(body) > 100_000:
        raise InvalidNoteAction("invalid body")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 1_000:
        raise InvalidNoteAction("invalid summary")
    if not isinstance(tags, list) or len(tags) > 20 or any(
        not isinstance(tag, str) or not tag.strip() or len(tag) > 64 for tag in tags
    ):
        raise InvalidNoteAction("invalid tags")
    if any(tag_error(tag) for tag in tags) or len({tag.casefold() for tag in tags}) != len(tags):
        raise InvalidNoteAction("invalid or duplicate tags")
    return NoteAction(title.strip(), body.strip(), tuple(tags), summary.strip())

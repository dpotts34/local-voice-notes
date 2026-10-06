#!/usr/bin/env python3
"""Read-only whole-vault lint with an explicitly selected canonical boundary.

No autofix, git operation, per-note selector, or symlink traversal.
Inline tag detection is conservative: never infer multiword tags from prose.
"""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import unicodedata
import uuid

import yaml
from markdown_it import MarkdownIt

from .note_action import tag_error
from .writer import slugify

MARKDOWN = MarkdownIt('commonmark')


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValueError('non-string or duplicate YAML property')
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def check_text(text, relative):
    issues = []
    properties = {}
    if text.startswith('---\n'):
        match = re.match(r'\A---\n(.*?)\n(?:---|\.\.\.)(?:\n|$)', text, re.S)
        if not match:
            return ['unclosed YAML properties']
        try:
            properties = yaml.load(match[1], Loader=UniqueLoader)
            if properties is None:
                properties = {}
            if not isinstance(properties, dict):
                return ['YAML properties must be a mapping']
        except (yaml.YAMLError, ValueError, TypeError) as error:
            return [f'invalid YAML: {error}']
        text = text[match.end():]
    if 'excalidraw-plugin' in properties:
        return []
    tags = properties.get('tags')
    if tags is not None:
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            issues.append('tags must be a list of strings (or empty)')
        else:
            for tag in tags:
                error = tag_error(tag)
                if error:
                    issues.append(f'tag {tag!r}: {error}')
            if len(tags) != len({t.casefold() for t in tags}):
                issues.append('duplicate tags (case-insensitive)')
    tokens = MARKDOWN.parse(text)
    first_title = None
    previous = 0
    for index, token in enumerate(tokens):
        if token.type == 'heading_open':
            level = int(token.tag[1:])
            if level > previous + 1:
                issues.append(f'skipped heading level H{previous} → H{level}')
            previous = level
            if level == 1 and first_title is None:
                first_title = tokens[index + 1].content
        if token.type != 'inline':
            continue
        in_link = 0
        for child in token.children or []:
            if child.type == 'link_open':
                in_link += 1
            elif child.type == 'link_close':
                in_link -= 1
            elif child.type == 'text' and not in_link:
                # ponytail: conservative candidates, not Obsidian's full tag parser;
                # never autofix these or infer intent from words after whitespace.
                for match in re.finditer(r'(?<![\w/#])#([\w/-]+)', child.content):
                    before = child.content[:match.start()].rsplit(None, 1)[-1:]
                    if before and '://' in before[0]:
                        continue
                    tag = match[1]
                    if tag.isnumeric():  # issue numbers are not Obsidian tags
                        continue
                    if error := tag_error(tag):
                        issues.append(f'inline tag {tag!r}: {error}')
    if relative.parent == Path('Voice Inbox'):
        if first_title is None:
            issues.append('Voice Inbox requires a title heading')
        elif not re.fullmatch(re.escape(slugify(first_title)) + r'(?: \([2-9]\d*\)| \(1\d+\))?', relative.stem):
            issues.append('Voice Inbox filename must be the title, optionally with (2) or higher')
        created = properties.get('created_at')
        try:
            parsed = created if isinstance(created, datetime) else datetime.fromisoformat(str(created))
            if parsed.tzinfo is None:
                raise ValueError('missing timezone')
        except ValueError:
            issues.append('created_at must retain a valid timestamp with timezone')
        thread_id = properties.get('thread_id')
        expected = f'[[Voice Threads/{thread_id}|Voice thread]]'
        try:
            valid_thread = isinstance(thread_id, str) and str(uuid.UUID(thread_id)) == thread_id
        except ValueError:
            valid_thread = False
        if not valid_thread or properties.get('thread') != expected:
            issues.append('Voice Inbox thread link must match thread_id')
    elif relative.parent == Path('Voice Threads'):
        thread_id = properties.get('thread_id')
        try:
            valid_thread = isinstance(thread_id, str) and str(uuid.UUID(thread_id)) == thread_id
        except ValueError:
            valid_thread = False
        if not valid_thread or relative.stem != thread_id:
            issues.append('Voice Threads filename must match thread_id')
    return issues


def scan(root):
    if (
        not root.is_absolute() or '..' in root.parts or root == Path(root.anchor)
        or root.resolve() != root or not root.is_dir()
    ):
        raise ValueError('vault must be an existing absolute canonical directory, not a symlink, traversal path, or filesystem root')
    count, issues = 0, []
    names = set()
    for directory, dirs, files in os.walk(
        root, followlinks=False,
        onerror=lambda error: issues.append(f'{error.filename}: {error.strerror}'),
    ):
        for name in list(dirs):
            path = Path(directory) / name
            if name.startswith('.'):
                dirs.remove(name)
            elif path.is_symlink():
                issues.append(f'{path.relative_to(root)}: skipped symlink')
                dirs.remove(name)
        for name in sorted(files):
            path = Path(directory) / name
            if name.startswith('.') or path.suffix.lower() != '.md':
                continue
            relative = path.relative_to(root)
            if path.is_symlink() or not path.is_file():
                issues.append(f'{relative}: skipped symlink or non-regular file')
                continue
            key = unicodedata.normalize('NFC', str(relative)).casefold()
            if key in names:
                issues.append(f'{relative}: case-insensitive filename collision')
            names.add(key)
            count += 1
            try:
                issues.extend(f'{relative}: {x}' for x in check_text(path.read_text(encoding='utf-8'), relative))
            except (OSError, UnicodeError) as error:
                issues.append(f'{relative}: {error}')
    return count, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', required=True, type=Path,
                        help='absolute canonical vault directory; all visible Markdown notes are scanned')
    args = parser.parse_args()
    try:
        count, issues = scan(args.vault)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print('\n'.join(issues))
    print(f'{count} notes checked; {len(issues)} findings; no files changed.')
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())

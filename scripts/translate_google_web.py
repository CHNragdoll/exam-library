#!/usr/bin/env python3
"""Fill eligible English paragraph sidecars using the Google Translate website.

The website's same-origin translation endpoint is undocumented. Its response is
validated on every request; an unexpected response never becomes a translation.
Run without --execute to inspect the queue. --execute translates at most one
paragraph unless --max-records or --all is supplied explicitly.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable


SITE_URL = "https://translate.google.com/?lfhs=2&sl=auto&tl=zh-CN&op=translate"
ENDPOINT = "https://translate.google.com/translate_a/single"
PROVIDER = "google-translate-web"
MAX_CHARS = 5000  # The website's displayed limit; count UTF-16 code units.
MAX_BATCH_PARAGRAPHS = 6  # Keep contextual bleed and segment mapping easy to audit.
MAX_BATCH_OPTIONS = 50  # Short independent choices still require exact marker roundtrip.
MARKER = "<<<GTSEG{:06d}>>>"
MARKER_RE = re.compile(r"<<<GTSEG(\d{6})>>>")
# Must match the manifest builder's exact tokenization, including a printed
# number attached to a blank such as "(26)_______".
BLANK_RE = re.compile(r"(?:\(\s*\d{1,3}\s*\)\s*)?[_＿](?:\s*[_＿])*")
PROTECTED_MARKER = "<<<GTPROTECT{:08d}>>>"
PROTECTED_MARKER_RE = re.compile(r"<<<GTPROTECT\d{8}>>>")
READABLE_MARKER_RE = re.compile(r"\[(?:BLANK|CUE)_[1-9]\d*\]")
HTML_ENTITY_RE = re.compile(r"&(?:\#[0-9]+|\#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);")
DEFAULT_INPUT = Path("data/sources/exam-library/structured/translations")
DEFAULT_STATE = Path(".local/google-translation-checkpoint.sqlite3")
EXPECTED_SIDECARS = 206
SAFE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


class TranslationError(RuntimeError):
    pass


class RetryableTranslationError(TranslationError):
    pass


class FatalTranslationError(TranslationError):
    """Provider or local storage is unusable; stop the corpus run immediately."""


class SourceEchoMismatch(TranslationError):
    """The provider echoed text other than the exact safe request payload."""


class SegmentationError(TranslationError):
    pass


class PlaceholderError(TranslationError):
    pass


class PartialBatchError(TranslationError):
    """A segmented batch had independently validated successes and failures."""

    def __init__(self, successes: list[tuple[Paragraph, str]],
                 failures: list[tuple[Paragraph, Exception]]):
        super().__init__(f"{len(failures)} of {len(successes) + len(failures)} records failed")
        self.successes = successes
        self.failures = failures


@dataclass(frozen=True)
class Paragraph:
    path: Path
    id: str
    source: str
    source_hash: str
    protected_blanks: tuple[str, ...] = ()
    collection: str = "paragraphs"
    protected_cues: tuple[str, ...] = ()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def transport_source(value: str) -> str:
    """Decode only complete HTML entities; source IDs and hashes stay unchanged."""
    return HTML_ENTITY_RE.sub(lambda match: html.unescape(match.group()), value)


def echo_difference(requested: str, echoed: str) -> str:
    position = next((i for i, (a, b) in enumerate(zip(requested, echoed)) if a != b),
                    min(len(requested), len(echoed)))
    return (f"source echo differs at character {position}: "
            f"request={requested[position:position + 24]!r}, echo={echoed[position:position + 24]!r}; "
            f"lengths {len(requested)}/{len(echoed)}")


def _printed_blank(match: re.Match, value: str) -> bool:
    token = match.group()
    if len(re.findall(r"[_＿]", token)) != 1 or token.lstrip().startswith("("):
        return True
    before = value[match.start() - 1:match.start()] if match.start() else ""
    after = value[match.end():match.end() + 1]
    return not (re.match(r"[A-Za-z0-9]", before) or re.match(r"[A-Za-z0-9]", after))


def blank_tokens(value: str) -> tuple[str, ...]:
    return tuple(match.group() for match in BLANK_RE.finditer(value)
                 if _printed_blank(match, value))


def all_blank_tokens(value: str) -> tuple[str, ...]:
    return tuple(match.group() for match in BLANK_RE.finditer(value))


def verified_blanks(source: str, metadata: object, paragraph_id: str) -> tuple[str, ...]:
    if not isinstance(metadata, list) or any(not isinstance(item, str) for item in metadata):
        raise TranslationError(f"Invalid protectedBlanks metadata: {paragraph_id}")
    found = blank_tokens(source)
    if tuple(metadata) not in (found, all_blank_tokens(source)):
        raise TranslationError(f"Protected blank metadata/source mismatch: {paragraph_id}")
    if "<<<GTPROTECT" in source or "<<<GTSEG" in source:
        raise TranslationError(f"Reserved marker appears in source: {paragraph_id}")
    return tuple(metadata)


def verified_cues(source: str, metadata: object, paragraph_id: str) -> tuple[str, ...]:
    if metadata is None:
        return ()
    if (not isinstance(metadata, list) or any(not isinstance(item, str) for item in metadata)
            or len(metadata) != len(set(metadata))):
        raise TranslationError(f"Invalid protectedCues metadata: {paragraph_id}")
    for cue in metadata:
        if (source.count(cue) != 1 or not re.fullmatch(r"[(（][^()（）]*[)）]", cue) or
                not re.search(r"[\u3400-\u9fff]", cue) or blank_tokens(cue)):
            raise TranslationError(f"Protected Chinese cue/source mismatch: {paragraph_id}")
    return tuple(metadata)


def validate_cues(expected: tuple[str, ...], translated: str) -> None:
    if any(translated.count(cue) != 1 for cue in expected):
        raise PlaceholderError("Translated Chinese cue differs from source")


def validate_blanks(expected: tuple[str, ...], translated: str) -> None:
    if (Counter(blank_tokens(translated)) != Counter(expected) and
            Counter(all_blank_tokens(translated)) != Counter(expected)):
        raise PlaceholderError("Translated blank tokens differ from source")


def protect_blanks(source: str, expected: tuple[str, ...]) -> tuple[str, tuple[tuple[str, str], ...]]:
    if not expected:
        return source, ()
    replacements: list[tuple[str, str]] = []
    protect_all = expected == all_blank_tokens(source)

    def replace(match: re.Match) -> str:
        if not protect_all and not _printed_blank(match, source):
            return match.group()
        marker = PROTECTED_MARKER.format(len(replacements) + 1)
        replacements.append((marker, match.group()))
        return marker

    protected = BLANK_RE.sub(replace, source)
    if tuple(token for _, token in replacements) != expected:
        raise AssertionError("Protected blank extraction changed")
    return protected, tuple(replacements)


def protect_source(source: str, blanks: tuple[str, ...],
                   cues: tuple[str, ...]) -> tuple[str, tuple[tuple[str, str], ...]]:
    protected, blank_replacements = protect_blanks(source, blanks)
    replacements = list(blank_replacements)
    for cue in cues:
        marker = PROTECTED_MARKER.format(len(replacements) + 1)
        if protected.count(cue) != 1:
            raise PlaceholderError("Chinese cue cannot be uniquely protected")
        protected = protected.replace(cue, marker, 1)
        replacements.append((marker, cue))
    replacements.sort(key=lambda row: protected.index(row[0]))
    return protected, tuple(replacements)


def protect_readable_source(source: str, blanks: tuple[str, ...],
                            cues: tuple[str, ...]) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Use plain markers only for a bounded English-language fallback request."""
    if READABLE_MARKER_RE.search(source) or "BLANK_" in source or "CUE_" in source:
        raise PlaceholderError("Readable marker collides with source text")
    without_cues = source
    for cue in cues:
        without_cues = without_cues.replace(cue, "", 1)
    if re.search(r"[\u3400-\u9fff]", without_cues):
        raise PlaceholderError("Unprotected Chinese text remains in fallback source")
    protected, original = protect_source(source, blanks, cues)
    blank_count = cue_count = 0
    readable = []
    for marker, token in original:
        if token in cues:
            cue_count += 1
            replacement = f"[CUE_{cue_count}]"
        else:
            blank_count += 1
            replacement = f"[BLANK_{blank_count}]"
        protected = protected.replace(marker, replacement, 1)
        readable.append((replacement, token))
    if not readable:
        raise PlaceholderError("Fallback requires a protected blank or Chinese cue")
    return protected, tuple(readable)


def restore_readable_source(translated: str,
                            replacements: tuple[tuple[str, str], ...]) -> str:
    observed = [match.group() for match in READABLE_MARKER_RE.finditer(translated)]
    if observed != [marker for marker, _ in replacements]:
        raise PlaceholderError("Google changed, dropped, or reordered readable markers")
    restored = translated
    for marker, token in replacements:
        restored = restored.replace(marker, token, 1)
    if "BLANK_" in restored or "CUE_" in restored:
        raise PlaceholderError("Unrestored readable marker remains")
    return restored


def restore_blanks(translated: str, replacements: tuple[tuple[str, str], ...]) -> str:
    found = [match.group() for match in PROTECTED_MARKER_RE.finditer(translated)]
    if found != [marker for marker, _ in replacements]:
        raise PlaceholderError("Google Translate changed, dropped, or reordered blank markers")
    restored = translated
    for marker, token in replacements:
        restored = restored.replace(marker, token, 1)
    if "GTPROTECT" in restored:
        raise PlaceholderError("Unrestored blank marker remains in translation")
    return restored


def json_paths(root: Path) -> list[Path]:
    if root.is_file():
        validate_sidecar_path(root)
        return [root]
    if not root.is_dir():
        raise TranslationError(f"Input sidecar path does not exist: {root}")
    paths = sorted(root.rglob("*.json"))
    if len(paths) != EXPECTED_SIDECARS:
        raise TranslationError(f"Expected {EXPECTED_SIDECARS} canonical sidecars in {root}; found {len(paths)}")
    paper_ids: set[str] = set()
    for path in paths:
        relative = path.relative_to(root)
        if len(relative.parts) != 2:
            raise TranslationError(f"Noncanonical or twin sidecar path: {path}")
        expected_id = validate_sidecar_path(path)
        if expected_id in paper_ids:
            raise TranslationError(f"Duplicate paper ID: {expected_id}")
        paper_ids.add(expected_id)
    return paths


def validate_sidecar_path(path: Path) -> str:
    if (path.is_symlink() or not SAFE_NAME_RE.fullmatch(path.parent.name) or
            not SAFE_NAME_RE.fullmatch(path.stem)):
        raise TranslationError(f"Noncanonical or twin sidecar path: {path}")
    expected_id = f"{path.parent.name}:{path.stem}"
    data, _ = read_sidecar(path)
    if data.get("paperId") != expected_id:
        raise TranslationError(f"Paper ID/path mismatch: {path}")
    return expected_id


def read_sidecar(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("paragraphs"), list):
        raise TranslationError(f"Invalid paragraphs sidecar: {path}")
    if "options" in data and not isinstance(data["options"], list):
        raise TranslationError(f"Invalid options sidecar: {path}")
    return data, raw


def eligible_paragraphs(paths: Iterable[Path], collection_filter: str = "all") -> tuple[list[Paragraph], int]:
    pending: list[Paragraph] = []
    complete = 0
    seen: set[str] = set()
    for path in paths:
        data, _ = read_sidecar(path)
        for collection, record in ((name, item)
                                   for name in ("paragraphs", "options")
                                   for item in data.get(name, [])):
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise TranslationError(f"Missing paragraph id in {path}")
            key = record["id"]
            if key in seen:
                raise TranslationError(f"Duplicate paragraph id: {key}")
            seen.add(key)
            if collection_filter != "all" and collection != collection_filter:
                continue
            if record.get("translationEligible") is not True:
                continue
            original = record.get("sourceText")
            if not isinstance(original, str) or record.get("sourceHash") != sha256(original):
                raise TranslationError(f"Source text hash mismatch: {key}")
            source = record.get("translationInput")
            declared_hash = record.get("translationInputHash")
            if not isinstance(source, str) or not source.strip():
                raise TranslationError(f"Eligible paragraph has no translation input: {key}")
            if declared_hash != sha256(source):
                raise TranslationError(f"Translation input hash mismatch: {key}")
            protected_blanks = verified_blanks(source, record.get("protectedBlanks"), key)
            protected_cues = verified_cues(source, record.get("protectedCues"), key)
            existing = record.get("translationZh")
            if existing is not None and not isinstance(existing, str):
                raise TranslationError(f"Unexpected translation value: {key}")
            if isinstance(existing, str) and existing.strip():
                validate_blanks(protected_blanks, existing)
                validate_cues(protected_cues, existing)
                complete += 1
            else:
                pending.append(Paragraph(path, key, source, declared_hash,
                                         protected_blanks, collection, protected_cues))
    return pending, complete


def split_long_text(value: str, limit: int = MAX_CHARS) -> list[str]:
    """Split at sentence/word boundaries, retaining every source character."""
    if utf16_length(value) <= limit:
        return [value]
    parts = []
    remaining = value
    while remaining:
        if utf16_length(remaining) <= limit:
            parts.append(remaining)
            break
        units = 0
        boundary = 0
        for i, char in enumerate(remaining):
            units += utf16_length(char)
            if units > limit:
                break
            boundary = i + 1
        head = remaining[:boundary]
        minimum = max(1, boundary // 2)
        sentence = max((m.end() for m in re.finditer(r"[.!?。！？][\s\n]*", head) if m.end() >= minimum), default=0)
        whitespace = max((m.end() for m in re.finditer(r"\s+", head) if m.end() >= minimum), default=0)
        cut = sentence or whitespace or boundary
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    if "".join(parts) != value or any(utf16_length(part) > limit for part in parts):
        raise AssertionError("Text splitting lost source characters")
    return parts


def build_batches(paragraphs: Iterable[Paragraph]) -> list[list[Paragraph]]:
    batches: list[list[Paragraph]] = []
    current: list[Paragraph] = []
    for paragraph in paragraphs:
        if paragraph.protected_blanks or paragraph.protected_cues:
            if current:
                batches.append(current)
                current = []
            batches.append([paragraph])
            continue
        if utf16_length(paragraph.source) > MAX_CHARS:
            if current:
                batches.append(current)
                current = []
            batches.append([paragraph])
            continue
        proposal = current + [paragraph]
        batch_limit = (MAX_BATCH_OPTIONS if paragraph.collection == "options"
                       else MAX_BATCH_PARAGRAPHS)
        if current and (current[-1].path != paragraph.path or
                        current[-1].collection != paragraph.collection or
                        len(proposal) > batch_limit or
                        utf16_length(batch_source(proposal)) > MAX_CHARS):
            batches.append(current)
            current = [paragraph]
        else:
            current = proposal
    if current:
        batches.append(current)
    return batches


def deduplicate_option_requests(records: Iterable[Paragraph]) -> tuple[list[Paragraph], dict[str, list[Paragraph]]]:
    """Share one request only for identical option input within the same paper."""
    representatives = []
    aliases: dict[str, list[Paragraph]] = {}
    owner_by_input = {}
    for record in records:
        key = ((record.path.resolve(), record.source_hash, record.source,
                record.protected_blanks, record.protected_cues)
               if record.collection == "options" else None)
        owner = owner_by_input.get(key) if key is not None else None
        if owner is None:
            representatives.append(record)
            aliases[record.id] = [record]
            if key is not None:
                owner_by_input[key] = record.id
        else:
            aliases[owner].append(record)
    return representatives, aliases


def batch_source(paragraphs: list[Paragraph]) -> str:
    if len(paragraphs) == 1:
        return protect_source(paragraphs[0].source, paragraphs[0].protected_blanks,
                              paragraphs[0].protected_cues)[0]
    if any(p.protected_blanks or p.protected_cues for p in paragraphs):
        raise AssertionError("Protected prompts must be translated individually")
    return "\n\n".join(f"{MARKER.format(i)}\n{p.source}" for i, p in enumerate(paragraphs, 1))


def minimum_request_count(batches: Iterable[list[Paragraph]]) -> int:
    count = 0
    for batch in batches:
        if len(batch) == 1:
            paragraph = batch[0]
            if paragraph.protected_blanks or paragraph.protected_cues:
                if utf16_length(batch_source(batch)) > MAX_CHARS:
                    raise TranslationError(f"Protected prompt exceeds 5,000 characters: {paragraph.id}")
                count += 1
            else:
                count += len(split_long_text(paragraph.source))
        else:
            count += 1
    return count


def parse_batch_result(value: str, count: int) -> list[str]:
    matches = list(MARKER_RE.finditer(value))
    if len(matches) != count or [int(m.group(1)) for m in matches] != list(range(1, count + 1)):
        raise SegmentationError("Google Translate changed or omitted batch delimiters")
    if value[:matches[0].start()].strip():
        raise SegmentationError("Unexpected text before first batch delimiter")
    results = [value[m.end():matches[i + 1].start() if i + 1 < count else len(value)].strip()
               for i, m in enumerate(matches)]
    if any(not part for part in results):
        raise SegmentationError("Empty segment in batch response")
    if any("GTSEG" in part for part in results):
        raise SegmentationError("Unparsed batch marker remains in translation")
    return results


def validate_translation(source: str, translated: str) -> str:
    result = translated.strip()
    if (not result or result == source.strip() or
            "GTPROTECT" in result or "GTSEG" in result or
            not re.search(r"[\u3400-\u9fff]", result)):
        raise TranslationError("Empty, unchanged, or non-Chinese translation response")
    return result


class RateLimiter:
    def __init__(self, interval: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        while True:
            with self.lock:
                now = self.clock()
                if now >= self.next_at:
                    self.next_at = now + self.interval
                    return
                delay = self.next_at - now
            # A concurrent 429 may extend next_at during this sleep.
            self.sleep(delay)

    def defer(self, seconds: float) -> None:
        """Make all workers honor a server-requested cooling-off period."""
        with self.lock:
            self.next_at = max(self.next_at, self.clock() + seconds)


class GoogleTranslateClient:
    def __init__(self, limiter: RateLimiter, attempts: int = 4,
                 opener: Callable = urllib.request.urlopen,
                 sleep: Callable[[float], None] = time.sleep, workers: int = 2):
        self.limiter = limiter
        self.attempts = attempts
        self.opener = opener
        self.sleep = sleep
        self.workers = workers

    def translate(self, source: str, *, source_language: str = "auto") -> str:
        if source_language not in {"auto", "en"}:
            raise ValueError("unsupported source language")
        request_source = transport_source(source)
        if not request_source or utf16_length(request_source) > MAX_CHARS:
            raise TranslationError("Request exceeds the Google Translate 5,000-character limit")
        body = urllib.parse.urlencode({"client": "gtx", "sl": source_language,
                                      "tl": "zh-CN", "dt": "t", "q": request_source}).encode()
        request = urllib.request.Request(
            ENDPOINT, data=body,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ExamLibraryTranslation/1.0)",
                     "Referer": SITE_URL, "Content-Type": "application/x-www-form-urlencoded"})
        for attempt in range(self.attempts):
            self.limiter.wait()
            try:
                with self.opener(request, timeout=30) as response:
                    if response.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                        raise RetryableTranslationError("Google Translate returned non-JSON content")
                    payload = json.load(response)
                if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
                    raise RetryableTranslationError("Google Translate response format changed")
                segments = payload[0]
                if not segments or any(not isinstance(item, list) or len(item) < 2 or
                                       not isinstance(item[0], str) or not isinstance(item[1], str)
                                       for item in segments):
                    raise RetryableTranslationError("Google Translate response segments changed")
                echoed_source = "".join(item[1] for item in segments)
                if echoed_source != request_source:
                    raise SourceEchoMismatch(echo_difference(request_source, echoed_source))
                return "".join(item[0] for item in segments)
            except urllib.error.HTTPError as exc:
                try:
                    if exc.code not in (408, 429, 500, 502, 503, 504):
                        raise FatalTranslationError(f"Google Translate HTTP {exc.code}") from exc
                    error: Exception = RetryableTranslationError(f"Google Translate HTTP {exc.code}")
                    retry_after = exc.headers.get("Retry-After")
                    if exc.code == 429:
                        self.limiter.defer(min(120.0, float(retry_after)) if retry_after and retry_after.isdecimal() else 30.0)
                finally:
                    exc.close()
            except (urllib.error.URLError, TimeoutError, ValueError, RetryableTranslationError) as exc:
                error = exc
                retry_after = None
            if attempt == self.attempts - 1:
                raise FatalTranslationError(f"Google Translate failed after {self.attempts} attempts: {error}") from error
            delay = min(60.0, 2 ** attempt + random.uniform(0, 0.5))
            if retry_after and retry_after.isdecimal():
                delay = max(delay, min(120.0, float(retry_after)))
            self.sleep(delay)
        raise AssertionError("Unreachable retry loop")


def translate_batch(paragraphs: list[Paragraph], client: GoogleTranslateClient) -> list[str]:
    if len(paragraphs) == 1:
        paragraph = paragraphs[0]
        if paragraph.protected_blanks or paragraph.protected_cues:
            source, replacements = protect_source(paragraph.source, paragraph.protected_blanks,
                                                   paragraph.protected_cues)
            if utf16_length(source) > MAX_CHARS:
                raise TranslationError(f"Protected prompt exceeds 5,000 characters: {paragraph.id}")
            for attempt in range(2):
                try:
                    translated = restore_blanks(client.translate(source), replacements)
                    if translated.strip() == paragraph.source.strip():
                        raise PlaceholderError("Google left a protected prompt untranslated")
                    result = validate_translation(paragraph.source, translated)
                    validate_blanks(paragraph.protected_blanks, result)
                    validate_cues(paragraph.protected_cues, result)
                    return [result]
                except PlaceholderError:
                    if attempt == 0:
                        continue
            fallback_source, readable = protect_readable_source(
                paragraph.source, paragraph.protected_blanks, paragraph.protected_cues)
            if utf16_length(fallback_source) > MAX_CHARS:
                raise TranslationError(f"Protected fallback exceeds 5,000 characters: {paragraph.id}")
            translated = restore_readable_source(
                client.translate(fallback_source, source_language="en"), readable)
            result = validate_translation(paragraph.source, translated)
            validate_blanks(paragraph.protected_blanks, result)
            validate_cues(paragraph.protected_cues, result)
            return [result]
        pieces = split_long_text(paragraph.source)
        result = validate_translation(paragraph.source,
                "".join(validate_translation(piece, client.translate(piece)) for piece in pieces))
        validate_blanks((), result)
        return [result]
    source = batch_source(paragraphs)
    if utf16_length(source) > MAX_CHARS:
        raise AssertionError("Batch exceeded source limit")
    raw = client.translate(source)
    try:
        parts = parse_batch_result(raw, len(paragraphs))
    except SegmentationError:
        parts = [None] * len(paragraphs)
    successes: list[tuple[Paragraph, str]] = []
    failures: list[tuple[Paragraph, Exception]] = []
    for paragraph, part in zip(paragraphs, parts):
        if part is not None:
            try:
                value = validate_translation(paragraph.source, part)
                validate_blanks((), value)
            except TranslationError:
                pass
            else:
                successes.append((paragraph, value))
                continue
        # A bad segment is retried alone. The other exact segments retain
        # their source-to-result mapping and can be checkpointed even if this
        # one ultimately fails.
        for attempt in range(2):
            try:
                value = translate_batch([paragraph], client)[0]
            except SourceEchoMismatch as exc:
                if attempt == 0:
                    continue
                failures.append((paragraph, exc))
            except FatalTranslationError:
                raise
            except Exception as exc:
                failures.append((paragraph, exc))
            else:
                successes.append((paragraph, value))
            break
    if failures:
        raise PartialBatchError(successes, failures)
    by_id = {paragraph.id: value for paragraph, value in successes}
    return [by_id[paragraph.id] for paragraph in paragraphs]


def open_checkpoint(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS translations (
        path TEXT NOT NULL, paragraph_id TEXT NOT NULL, source_hash TEXT NOT NULL,
        translation TEXT NOT NULL, provider TEXT NOT NULL, translated_at TEXT NOT NULL,
        PRIMARY KEY (path, paragraph_id, source_hash))""")
    db.execute("""CREATE TABLE IF NOT EXISTS rejected_translations (
        path TEXT NOT NULL, paragraph_id TEXT NOT NULL, source_hash TEXT NOT NULL,
        reason TEXT NOT NULL, raw_translation TEXT, rejected_at TEXT NOT NULL,
        PRIMARY KEY (path, paragraph_id, source_hash))""")
    db.commit()
    return db


def paragraph_key(paragraph: Paragraph) -> tuple[str, str, str]:
    return str(paragraph.path.resolve()), paragraph.id, paragraph.source_hash


def quarantined_keys(db: sqlite3.Connection) -> set[tuple[str, str, str]]:
    try:
        return set(db.execute("SELECT path, paragraph_id, source_hash FROM rejected_translations"))
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        return set()


def read_quarantined_keys(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return quarantined_keys(db)


def quarantine(db: sqlite3.Connection, paragraph: Paragraph, reason: str,
               raw_translation: str | None = None) -> None:
    if not reason.strip():
        raise ValueError("Quarantine reason is required")
    key = paragraph_key(paragraph)
    with db:
        db.execute("DELETE FROM translations WHERE path=? AND paragraph_id=? AND source_hash=?", key)
        db.execute("""INSERT OR REPLACE INTO rejected_translations
            (path, paragraph_id, source_hash, reason, raw_translation, rejected_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (*key, reason, raw_translation, dt.datetime.now(dt.timezone.utc).isoformat()))


def save_batch(db: sqlite3.Connection, paragraphs: list[Paragraph], results: list[str]) -> None:
    if len(paragraphs) != len(results):
        raise AssertionError("Translation result count mismatch")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with db:
        db.executemany("""INSERT OR REPLACE INTO translations
            (path, paragraph_id, source_hash, translation, provider, translated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [(str(p.path.resolve()), p.id, p.source_hash, value, PROVIDER, now)
             for p, value in zip(paragraphs, results)])


def atomic_json_write(path: Path, data: dict, old_raw: str) -> None:
    pretty = "\n" in old_raw
    content = json.dumps(data, ensure_ascii=False, indent=2 if pretty else None,
                         separators=None if pretty else (",", ":")) + ("\n" if old_raw.endswith("\n") else "")
    mode = path.stat().st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_text(encoding="utf-8") != old_raw:
            raise TranslationError(f"Sidecar changed while translation was being saved: {path}")
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_checkpoint(db: sqlite3.Connection, paths: Iterable[Path],
                     collection_filter: str = "all") -> int:
    written = 0
    rejected = quarantined_keys(db)
    for path in sorted(set(paths)):
        data, raw = read_sidecar(path)
        changed = False
        for collection, record in ((name, item)
                                   for name in ("paragraphs", "options")
                                   for item in data.get(name, [])):
            if collection_filter != "all" and collection != collection_filter:
                continue
            if record.get("translationEligible") is not True or record.get("translationZh"):
                continue
            source = record.get("translationInput")
            digest = record.get("translationInputHash")
            original = record.get("sourceText")
            if not isinstance(original, str) or record.get("sourceHash") != sha256(original):
                raise TranslationError(f"Source text changed or hash is invalid: {record.get('id')}")
            if not isinstance(source, str) or digest != sha256(source):
                raise TranslationError(f"Translation input changed or hash is invalid: {record.get('id')}")
            protected_blanks = verified_blanks(source, record.get("protectedBlanks"), record["id"])
            protected_cues = verified_cues(source, record.get("protectedCues"), record["id"])
            if (str(path.resolve()), record["id"], digest) in rejected:
                continue
            row = db.execute("""SELECT translation FROM translations
                WHERE path=? AND paragraph_id=? AND source_hash=?""",
                (str(path.resolve()), record["id"], digest)).fetchone()
            if row:
                translated = validate_translation(source, row[0])
                validate_blanks(protected_blanks, translated)
                validate_cues(protected_cues, translated)
                record["translationZh"] = translated
                changed = True
                written += 1
        if changed:
            # Reloading each file immediately before this write keeps unrelated
            # fields and already completed translations in the current sidecar.
            atomic_json_write(path, data, raw)
    return written


def run(paths: list[Path], state: Path, client: GoogleTranslateClient,
        max_records: int | None, selected_ids: set[str] | None = None,
        collection_filter: str = "all") -> tuple[int, int]:
    db = open_checkpoint(state)
    try:
        apply_checkpoint(db, paths, collection_filter)
        pending, _ = eligible_paragraphs(paths, collection_filter)
        rejected = quarantined_keys(db)
        pending = [p for p in pending if paragraph_key(p) not in rejected]
        if selected_ids is not None:
            present = {p.id for p in pending}
            if selected_ids - present:
                raise TranslationError(f"Requested paragraph IDs are not pending: {sorted(selected_ids - present)}")
            pending = [p for p in pending if p.id in selected_ids]
        elif max_records is not None:
            pending = pending[:max_records]
        representatives, aliases = deduplicate_option_requests(pending)
        batches = build_batches(representatives)
        translated = 0
        errors = 0
        def fanout(batch: list[Paragraph], results: list[str]) -> tuple[list[Paragraph], list[str]]:
            records = []
            values = []
            for paragraph, value in zip(batch, results):
                copies = aliases[paragraph.id]
                records.extend(copies)
                values.extend([value] * len(copies))
            return records, values

        # All writes remain on the main thread; only HTTP requests are parallel.
        with concurrent.futures.ThreadPoolExecutor(max_workers=client.workers) as pool:
            queue = iter(batches)
            futures: dict[concurrent.futures.Future, list[Paragraph]] = {}

            def enqueue() -> None:
                batch = next(queue, None)
                if batch is not None:
                    futures[pool.submit(translate_batch, batch, client)] = batch

            for _ in range(client.workers):
                enqueue()
            while futures:
                finished, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in finished:
                    batch = futures.pop(future)
                    try:
                        results = future.result()
                    except FatalTranslationError:
                        for other in futures:
                            other.cancel()
                        raise
                    except PartialBatchError as exc:
                        if exc.successes:
                            good_records, good_values = fanout(
                                [paragraph for paragraph, _ in exc.successes],
                                [value for _, value in exc.successes])
                            save_batch(db, good_records, good_values)
                            apply_checkpoint(db, [record.path for record in good_records],
                                             collection_filter)
                            translated += len(good_records)
                            print(f"Translated {translated}/{len(pending)} paragraphs", file=sys.stderr)
                        for paragraph, failure in exc.failures:
                            copies = aliases[paragraph.id]
                            if isinstance(failure, SourceEchoMismatch):
                                for copy in copies:
                                    quarantine(db, copy,
                                               f"Persistent source echo mismatch: {failure}")
                            errors += len(copies)
                            print(f"Failed {paragraph.id}: {failure}", file=sys.stderr)
                    except SourceEchoMismatch as exc:
                        print(f"Batch source echo mismatch for IDs {[p.id for p in batch]}: {exc}; retrying individually",
                              file=sys.stderr)
                        for paragraph in batch:
                            for attempt in range(2):
                                try:
                                    result = translate_batch([paragraph], client)
                                except SourceEchoMismatch as individual_error:
                                    if attempt == 0:
                                        continue
                                    for copy in aliases[paragraph.id]:
                                        quarantine(db, copy, f"Persistent source echo mismatch: {individual_error}")
                                    errors += len(aliases[paragraph.id])
                                    print(f"Quarantined {paragraph.id}: {individual_error}", file=sys.stderr)
                                except FatalTranslationError:
                                    for other in futures:
                                        other.cancel()
                                    raise
                                except Exception as individual_error:
                                    errors += len(aliases[paragraph.id])
                                    print(f"Failed {paragraph.id}: {individual_error}", file=sys.stderr)
                                else:
                                    expanded, values = fanout([paragraph], result)
                                    save_batch(db, expanded, values)
                                    apply_checkpoint(db, [copy.path for copy in expanded], collection_filter)
                                    translated += len(expanded)
                                    print(f"Translated {translated}/{len(pending)} paragraphs", file=sys.stderr)
                                break
                    except Exception as exc:
                        errors += sum(len(aliases[paragraph.id]) for paragraph in batch)
                        print(f"Failed IDs {[p.id for p in batch]}: {exc}", file=sys.stderr)
                    else:
                        # Checkpoint or sidecar failures must stop immediately.
                        expanded, values = fanout(batch, results)
                        save_batch(db, expanded, values)
                        apply_checkpoint(db, [p.path for p in expanded], collection_filter)
                        translated += len(expanded)
                        print(f"Translated {translated}/{len(pending)} paragraphs", file=sys.stderr)
                    enqueue()
        return translated, errors
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Sidecar JSON file or directory")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="Durable SQLite checkpoint")
    parser.add_argument("--execute", action="store_true", help="Send text to Google Translate")
    parser.add_argument("--collection", choices=("all", "paragraphs", "options"), default="all",
                        help="Translate only paragraphs or options (default: both)")
    parser.add_argument("--id", action="append", dest="ids", help="Translate only this exact paragraph ID (repeatable)")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true", help="Translate all pending paragraphs")
    scope.add_argument("--max-records", type=int, default=1, help="Maximum records this run (default: 1)")
    parser.add_argument("--workers", type=int, default=2, help="Parallel requests (1 to 4)")
    parser.add_argument("--min-interval", type=float, default=1.5, help="Seconds between request starts")
    parser.add_argument("--attempts", type=int, default=4, help="Retries per request (1 to 8)")
    args = parser.parse_args(argv)
    if args.ids and args.all:
        parser.error("--id cannot be combined with --all")
    if args.ids and len(set(args.ids)) != len(args.ids):
        parser.error("Duplicate --id")
    if args.max_records is not None and args.max_records < 1 or not 1 <= args.workers <= 4 or args.min_interval < 0.5 or not 1 <= args.attempts <= 8:
        parser.error("Invalid record limit, workers, interval, or attempts")
    try:
        paths = json_paths(args.input)
        pending, complete = eligible_paragraphs(paths, args.collection)
        rejected = read_quarantined_keys(args.state)
        quarantined = sum(paragraph_key(p) in rejected for p in pending)
        pending = [p for p in pending if paragraph_key(p) not in rejected]
        batches = build_batches(pending)
        minimum_requests = minimum_request_count(batches)
        selected_ids = set(args.ids) if args.ids else None
        if selected_ids is not None:
            available = {p.id for p in pending}
            if selected_ids - available:
                raise TranslationError(f"Requested paragraph IDs are not pending: {sorted(selected_ids - available)}")
        selected = len(selected_ids) if selected_ids is not None else (len(pending) if args.all else min(len(pending), args.max_records))
        print(json.dumps({"files": len(paths), "pending": len(pending), "quarantined": quarantined,
                          "alreadyTranslated": complete,
                          "selected": selected, "plannedBatches": len(batches),
                          "minimumCorpusRequests": minimum_requests,
                          "rateLimitFloorMinutes": round(max(0, minimum_requests - 1) * args.min_interval / 60, 1)},
                         ensure_ascii=False))
        if not args.execute:
            return 0
        client = GoogleTranslateClient(RateLimiter(args.min_interval), attempts=args.attempts,
                                       workers=args.workers)
        done, failed = run(paths, args.state, client,
                           None if args.all else args.max_records, selected_ids,
                           args.collection)
        print(json.dumps({"translated": done, "failed": failed}, ensure_ascii=False))
        return 1 if failed else 0
    except (OSError, ValueError, TranslationError, sqlite3.Error) as exc:
        print(f"Translation stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

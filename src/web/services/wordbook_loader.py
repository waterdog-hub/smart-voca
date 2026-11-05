#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 운영자가 CSV 파일로 공용 단어장을 DB에 넣는 규칙 (결정 D-WB05)
# 파일 위치: src/web/services/wordbook_loader.py
#
# 회원이 쓰는 기능이 아니라 운영자의 명령줄 도구(ai-agent/scripts/load_wordbooks.py)가 부른다.

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from core.word_service import WordService
from web.db.tables import Wordbook
from web.repositories import wordbook_repository
from web.security import csv_guard

MAX_WORD_LENGTH = 100
MAX_MEANING_LENGTH = 500
MAX_TITLE_LENGTH = 100
MAX_WORDBOOK_ROWS = 5000
MAX_REPORTED_INVALID_ROWS = 100
CSV_HEADER = ["word", "meaning"]
# 주소와 파일 이름에 쓰일 수 있도록 영문 소문자, 숫자, 하이픈만 허용한다
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")


class WordbookFileError(ValueError):
    """운영자가 고쳐야 하는 파일이나 목록 파일의 문제."""


@dataclass
class WordbookSpec:
    slug: str
    title: str
    description: str
    source_note: str
    file: Path
    # (시작, 끝) 데이터 행 번호. 1부터 세고 끝을 포함한다. 없으면 파일 전체다
    row_range: tuple[int, int] | None = None


@dataclass
class ParsedWordbook:
    entries: list[tuple[str, str, str]] = field(default_factory=list)  # (단어, 단어 키, 뜻)
    skipped_duplicate: int = 0
    invalid_rows: list[tuple[int, str]] = field(default_factory=list)
    invalid_count: int = 0


@dataclass
class LoadResult:
    slug: str
    created: bool
    entry_count: int
    skipped_duplicate: int
    invalid_count: int
    invalid_rows: list[tuple[int, str]]


def normalize_meaning(meaning_text: str) -> str:
    # '달리다/ /운영하다'처럼 빈 칸이 섞인 입력을 데스크톱 앱과 같은 규칙으로 정리한다
    return "/".join(WordService.split_meanings(meaning_text))


def find_word_problems(word_text: str, meaning_text: str) -> dict[str, str]:
    problems = {}
    if WordService.validate(word_text, meaning_text, []):
        message = "단어와 뜻을 모두 입력하세요."
        if not word_text:
            problems["word"] = message
        if not meaning_text:
            problems["meaning"] = message
    if len(word_text) > MAX_WORD_LENGTH:
        problems["word"] = f"단어는 {MAX_WORD_LENGTH}자 이하여야 합니다."
    elif word_text and not word_text.isprintable():
        problems["word"] = "단어에 쓸 수 없는 문자가 있습니다."
    if len(meaning_text) > MAX_MEANING_LENGTH:
        problems["meaning"] = f"뜻은 {MAX_MEANING_LENGTH}자 이하여야 합니다."
    elif meaning_text and not meaning_text.isprintable():
        problems["meaning"] = "뜻에 쓸 수 없는 문자가 있습니다."
    return problems


def parse_wordbook_csv(raw: bytes, row_range: tuple[int, int] | None = None) -> ParsedWordbook:
    if len(raw) > csv_guard.MAX_UPLOAD_BYTES:
        raise WordbookFileError("파일은 5MB 이하여야 합니다.")
    text = csv_guard.decode_upload(raw)
    if text is None:
        raise WordbookFileError("파일을 읽을 수 없습니다. UTF-8 또는 CP949 CSV 파일이어야 합니다.")
    reader = csv.reader(io.StringIO(text, newline=""))
    parsed = ParsedWordbook()
    seen_keys: set[str] = set()
    data_row_number = 0
    try:
        if [column.strip() for column in next(reader, [])] != CSV_HEADER:
            raise WordbookFileError("첫 줄은 word,meaning이어야 합니다.")
        for columns in reader:
            if not columns:
                continue  # 빈 줄은 오류가 아니다
            data_row_number += 1
            if row_range is not None:
                if data_row_number < row_range[0]:
                    continue
                if data_row_number > row_range[1]:
                    break
            if len(parsed.entries) + parsed.invalid_count >= MAX_WORDBOOK_ROWS:
                raise WordbookFileError(f"단어장은 {MAX_WORDBOOK_ROWS:,}행 이하여야 합니다.")
            _add_row(parsed, seen_keys, reader.line_num, columns)
    except csv.Error:
        raise WordbookFileError("CSV 형식이 올바르지 않습니다.") from None
    return parsed


def _add_row(
    parsed: ParsedWordbook, seen_keys: set[str], line_number: int, columns: list[str]
) -> None:
    if len(columns) < 2 or any(column.strip() for column in columns[2:]):
        _record_invalid(parsed, line_number, "열은 word,meaning 두 개여야 합니다.")
        return
    word_text = columns[0].strip()
    meaning_text = normalize_meaning(columns[1].strip())
    problems = find_word_problems(word_text, meaning_text)
    if problems:
        _record_invalid(parsed, line_number, next(iter(problems.values())))
        return
    word_key = word_text.lower()
    if word_key in seen_keys:
        parsed.skipped_duplicate += 1
        return
    seen_keys.add(word_key)
    parsed.entries.append((word_text, word_key, meaning_text))


def _record_invalid(parsed: ParsedWordbook, line_number: int, reason: str) -> None:
    parsed.invalid_count += 1
    if len(parsed.invalid_rows) < MAX_REPORTED_INVALID_ROWS:
        parsed.invalid_rows.append((line_number, reason))


def load_wordbook(db: Session, spec: WordbookSpec) -> LoadResult:
    """단어장 하나를 DB에 넣는다. 같은 slug가 있으면 정보와 항목을 통째로 바꾼다."""
    try:
        raw = spec.file.read_bytes()
    except OSError as error:
        raise WordbookFileError(f"{spec.file.name} 파일을 읽을 수 없습니다: {error}") from None
    parsed = parse_wordbook_csv(raw, spec.row_range)
    # 비어 있는 파일로 잘못 불러와 기존 단어장을 비우는 일을 막는다
    if not parsed.entries:
        raise WordbookFileError(f"{spec.slug}: 넣을 수 있는 단어가 없습니다.")
    book = wordbook_repository.find_by_slug(db, spec.slug)
    created = book is None
    if created:
        book = Wordbook(slug=spec.slug, title="", description="", source_note="")
        db.add(book)
    book.title, book.description, book.source_note = spec.title, spec.description, spec.source_note
    db.flush()
    # 회원이 이미 담은 단어는 복사본이라 항목을 바꿔도 영향이 없다 (D-WB02)
    entry_count = wordbook_repository.replace_entries(db, book.id, parsed.entries)
    db.commit()
    return LoadResult(
        spec.slug, created, entry_count, parsed.skipped_duplicate,
        parsed.invalid_count, parsed.invalid_rows,
    )


def read_manifest(manifest_path: Path) -> list[WordbookSpec]:
    """목록 파일을 읽는다. 단어장 파일 경로는 목록 파일이 있는 폴더 안이어야 한다."""
    try:
        document = json.loads(manifest_path.read_text("utf-8"))
        items = document["wordbooks"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise WordbookFileError(f"목록 파일을 읽을 수 없습니다: {manifest_path} ({error})") from None
    if not isinstance(items, list) or not items:
        raise WordbookFileError("목록 파일에 wordbooks가 비어 있습니다.")
    base_dir = manifest_path.parent.resolve()
    specs = [_make_spec(item, base_dir) for item in items]
    slugs = [spec.slug for spec in specs]
    if len(set(slugs)) != len(slugs):
        raise WordbookFileError("목록 파일에 같은 slug가 두 번 나옵니다.")
    return specs


def _make_spec(item: object, base_dir: Path) -> WordbookSpec:
    if not isinstance(item, dict):
        raise WordbookFileError("wordbooks의 각 항목은 객체여야 합니다.")
    slug = item.get("slug")
    if not isinstance(slug, str) or not SLUG_PATTERN.match(slug):
        raise WordbookFileError(f"slug는 영문 소문자, 숫자, 하이픈 50자 이하여야 합니다: {slug!r}")
    texts = {}
    for name in ("title", "description", "source_note", "file"):
        value = item.get(name)
        if not isinstance(value, str) or not value.strip():
            raise WordbookFileError(f"{slug}: {name}이 비어 있습니다.")
        texts[name] = value.strip()
    if len(texts["title"]) > MAX_TITLE_LENGTH:
        raise WordbookFileError(f"{slug}: title은 {MAX_TITLE_LENGTH}자 이하여야 합니다.")
    file_path = (base_dir / texts["file"]).resolve()
    if not file_path.is_relative_to(base_dir):
        raise WordbookFileError(f"{slug}: file은 목록 파일이 있는 폴더 안에 있어야 합니다.")
    return WordbookSpec(
        slug, texts["title"], texts["description"], texts["source_note"], file_path,
        _read_row_range(slug, item.get("rows")),
    )


def _read_row_range(slug: str, value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    valid = (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(number, int) and not isinstance(number, bool) for number in value)
        and 1 <= value[0] <= value[1]
    )
    if not valid:
        raise WordbookFileError(f"{slug}: rows는 [시작, 끝] 형식의 1 이상 정수여야 합니다.")
    return value[0], value[1]


def load_manifest(db: Session, manifest_path: Path) -> list[LoadResult]:
    return [load_wordbook(db, spec) for spec in read_manifest(manifest_path)]

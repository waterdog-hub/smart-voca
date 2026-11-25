#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 웹 내 단어 조회·직접 등록·수정·삭제·CSV 가져오기 규칙
# 파일 위치: src/web/services/word_service_web.py
#
# 2026-11-25 기말 과제 요건(VOCA-FR-001~003)에 맞춰 회원이 직접 단어를 등록·수정·삭제하고
# CSV로 한꺼번에 가져오는 기능을 다시 넣었다. 공용 단어장 담기·제외(결정 D-WB04)는 그대로 둔다.
#
# 중복 처리 규칙 (VOCA-FR-003, 결정 D-VOCA03):
# - 대소문자만 다른 단어는 같은 단어로 본다 (설계서 D-24)
# - 직접 등록·수정에서 이미 있는 단어면 저장하지 않고 알린다 (409)
# - CSV 가져오기에서 이미 있는 단어와 파일 안에서 두 번째로 나온 단어는 건너뛴다. 기존 뜻은 바꾸지 않는다
# - 예전에 지운 단어를 다시 등록하면 그 행을 되살려 학습 기록을 이어 간다

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.db.base import utc_now
from web.db.tables import Word
from web.errors import ApiError
from web.repositories import word_repository
from web.security import csv_guard
from web.services.wordbook_loader import find_word_problems, normalize_meaning

# 제공 CSV의 첫 줄은 "영단어,뜻"이다. 운영자 단어장 형식(word,meaning)도 받는다
CSV_HEADERS = (["영단어", "뜻"], ["word", "meaning"])
MAX_IMPORT_ROWS = 5000
MAX_REPORTED_PROBLEMS = 20


@dataclass
class ImportResult:
    added: int = 0  # 새로 등록한 단어 수 (되살린 단어 포함)
    skipped_existing: int = 0  # 이미 있어 건너뛴 단어 수
    skipped_duplicate: int = 0  # 파일 안에서 중복이라 건너뛴 수
    invalid_count: int = 0  # 형식 오류로 건너뛴 줄 수
    problems: list[str] = field(default_factory=list)  # 앞의 몇 줄만 화면에 보여 준다


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "단어를 찾을 수 없습니다.")


def _duplicate(word_text: str) -> ApiError:
    return ApiError(
        409, "WORD_EXISTS", "이미 등록된 단어입니다.", fields={"word": f"'{word_text}'는 이미 있습니다."}
    )


def _clean(word_text: str, meaning_text: str) -> tuple[str, str]:
    word_text = word_text.strip()
    meaning_text = normalize_meaning(meaning_text.strip())
    problems = find_word_problems(word_text, meaning_text)
    if problems:
        raise ApiError(422, "VALIDATION_FAILED", "입력값을 확인해 주세요.", fields=problems)
    return word_text, meaning_text


class WebWordService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def list_words(
        self, keyword: str, sort: str, order: str, limit: int, offset: int
    ) -> tuple[list[Word], int]:
        needle = keyword.strip().lower()
        return word_repository.list_words(self.db, self.user_id, needle, sort, order, limit, offset)

    def add_word(self, word_text: str, meaning_text: str) -> Word:
        word_text, meaning_text = _clean(word_text, meaning_text)
        word_key = word_text.lower()
        if word_repository.find_active_by_key(self.db, self.user_id, word_key) is not None:
            raise _duplicate(word_text)
        row = word_repository.find_latest_deleted_by_key(self.db, self.user_id, word_key)
        if row is not None:
            # 지웠던 단어를 다시 등록하면 학습 기록을 이어 간다
            row.word, row.meaning, row.deleted_at = word_text, meaning_text, None
        else:
            row = word_repository.add_word(self.db, self.user_id, word_text, word_key, meaning_text)
        self._commit(word_text)
        return row

    def update_word(self, word_id: int, word_text: str, meaning_text: str) -> Word:
        row = word_repository.get_active_word(self.db, self.user_id, word_id)
        if row is None:
            raise _not_found()
        word_text, meaning_text = _clean(word_text, meaning_text)
        word_key = word_text.lower()
        other = word_repository.find_active_by_key(self.db, self.user_id, word_key)
        if other is not None and other.id != row.id:
            raise _duplicate(word_text)
        row.word, row.word_key, row.meaning = word_text, word_key, meaning_text
        self._commit(word_text)
        return row

    def delete_word(self, word_id: int) -> None:
        # 진도에서는 빼고 학습·시험 기록은 남긴다 (D-12, D-W07)
        if word_repository.soft_delete_words(self.db, self.user_id, [word_id], utc_now()) == 0:
            raise _not_found()
        self.db.commit()

    def import_csv(self, raw: bytes) -> ImportResult:
        text = self._decode(raw)
        existing_rows = word_repository.list_all_words_including_deleted(self.db, self.user_id)
        active_keys = {row.word_key for row in existing_rows if row.deleted_at is None}
        # 삭제 시각 오름차순이라 같은 키는 가장 최근에 지운 행이 사전에 남는다
        deleted_rows = {row.word_key: row for row in existing_rows if row.deleted_at is not None}
        seen_keys: set[str] = set()
        result = ImportResult()
        reader = csv.reader(io.StringIO(text, newline=""))
        try:
            for columns in reader:
                if not columns or not any(column.strip() for column in columns):
                    continue  # 빈 줄은 오류가 아니다
                if reader.line_num == 1 and [c.strip().lower() for c in columns[:2]] in CSV_HEADERS:
                    continue  # 첫 줄 제목
                if result.added + result.skipped_existing + result.skipped_duplicate + result.invalid_count >= MAX_IMPORT_ROWS:
                    raise ApiError(422, "CSV_TOO_LARGE", f"한 번에 {MAX_IMPORT_ROWS:,}줄까지 가져올 수 있습니다.")
                self._import_row(result, columns, reader.line_num, seen_keys, active_keys, deleted_rows)
        except csv.Error:
            self.db.rollback()
            raise ApiError(422, "CSV_INVALID", "CSV 형식이 올바르지 않습니다.") from None
        except ApiError:
            self.db.rollback()
            raise
        self._commit("CSV")
        return result

    def _import_row(self, result, columns, line_number, seen_keys, active_keys, deleted_rows) -> None:
        if len(columns) < 2 or any(column.strip() for column in columns[2:]):
            self._invalid(result, line_number, "열은 영단어,뜻 두 개여야 합니다.")
            return
        word_text = columns[0].strip()
        meaning_text = normalize_meaning(columns[1].strip())
        problems = find_word_problems(word_text, meaning_text)
        if problems:
            self._invalid(result, line_number, next(iter(problems.values())))
            return
        word_key = word_text.lower()
        if word_key in seen_keys:
            result.skipped_duplicate += 1
            return
        seen_keys.add(word_key)
        if word_key in active_keys:
            result.skipped_existing += 1
            return
        revived = deleted_rows.pop(word_key, None)
        if revived is not None:
            revived.word, revived.meaning, revived.deleted_at = word_text, meaning_text, None
        else:
            word_repository.add_word(self.db, self.user_id, word_text, word_key, meaning_text)
        result.added += 1

    @staticmethod
    def _invalid(result: ImportResult, line_number: int, reason: str) -> None:
        result.invalid_count += 1
        if len(result.problems) < MAX_REPORTED_PROBLEMS:
            result.problems.append(f"{line_number}번째 줄: {reason}")

    @staticmethod
    def _decode(raw: bytes) -> str:
        if not raw:
            raise ApiError(422, "CSV_EMPTY", "빈 파일입니다.")
        if len(raw) > csv_guard.MAX_UPLOAD_BYTES:
            raise ApiError(413, "CSV_TOO_LARGE", "파일은 5MB 이하여야 합니다.")
        # 업로드 파일은 디스크에 쓰지 않고 메모리에서 처리한다 (서버는 /data, /tmp 외에는 쓸 수 없다)
        text = csv_guard.decode_upload(raw)
        if text is None:
            raise ApiError(422, "CSV_ENCODING", "파일을 읽을 수 없습니다. UTF-8 또는 CP949 CSV 파일이어야 합니다.")
        return text

    def _commit(self, label: str) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            # 같은 회원이 동시에 같은 단어를 등록하면 유일 제약이 막는다
            self.db.rollback()
            raise _duplicate(label) from None

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 웹 단어장 규칙 (추가, 수정, 삭제, CSV 가져오기·내보내기)
# 파일 위치: src/web/services/word_service_web.py

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.word_service import WordService
from web.db.base import utc_now
from web.db.tables import Word
from web.errors import ApiError
from web.repositories import auth_repository, word_repository
from web.security import csv_guard, rate_limit

MAX_WORD_LENGTH = 100
MAX_MEANING_LENGTH = 500
MAX_REPORTED_INVALID_ROWS = 100
CSV_HEADER = ["word", "meaning"]
CSV_HEADER_ERROR = "단어 파일 형식이 맞지 않습니다. 첫 줄은 word,meaning이어야 합니다."


@dataclass
class ImportResult:
    added: int = 0
    skipped_duplicate: int = 0
    skipped_invalid: int = 0
    invalid_rows: list[dict[str, object]] = field(default_factory=list)


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


def _invalid_input(problems: dict[str, str]) -> ApiError:
    return ApiError(400, "VALIDATION_FAILED", "입력값을 확인해 주세요.", fields=problems)


def _duplicate_error(existing_word: str) -> ApiError:
    message = f"이미 있는 단어입니다: {existing_word}"
    return ApiError(409, "WORD_DUPLICATE", message, fields={"word": message})


def _file_error(message: str) -> ApiError:
    return ApiError(400, "VALIDATION_FAILED", message, fields={"file": message})


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "단어를 찾을 수 없습니다.")


class WebWordService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def list_words(
        self, keyword: str, sort: str, order: str, limit: int, offset: int
    ) -> tuple[list[Word], int]:
        needle = keyword.strip().lower()
        return word_repository.list_words(self.db, self.user_id, needle, sort, order, limit, offset)

    def _conflicting_word_text(self, word_key: str) -> str:
        # 동시 요청에 진 쪽이 받는 안내다. 그사이 상대가 지웠다면 입력한 키를 대신 보여 준다
        self.db.rollback()
        existing = word_repository.find_active_by_key(self.db, self.user_id, word_key)
        return existing.word if existing is not None else word_key

    def add_word(self, word_text: str, meaning_text: str) -> Word:
        word_text = word_text.strip()
        meaning_text = normalize_meaning(meaning_text)
        problems = find_word_problems(word_text, meaning_text)
        if problems:
            raise _invalid_input(problems)
        word_key = word_text.lower()
        existing = word_repository.find_active_by_key(self.db, self.user_id, word_key)
        if existing is not None:
            raise _duplicate_error(existing.word)
        row = word_repository.find_latest_deleted_by_key(self.db, self.user_id, word_key)
        if row is not None:
            # 지웠던 단어를 다시 쓰면 이전 학습 기록을 이어 간다 (데이터 모델 §4.1)
            row.word, row.meaning, row.deleted_at = word_text, meaning_text, None
        else:
            row = word_repository.add_word(
                self.db, self.user_id, word_text, word_key, meaning_text
            )
        try:
            self.db.commit()
        except IntegrityError:
            # 앞의 검사와 저장 사이에 같은 단어가 들어온 경우 유일 인덱스가 막는다
            raise _duplicate_error(self._conflicting_word_text(word_key)) from None
        return row

    def update_word(self, word_id: int, word_text: str | None, meaning_text: str | None) -> Word:
        row = word_repository.get_active_word(self.db, self.user_id, word_id)
        if row is None:
            raise _not_found()
        new_word = row.word if word_text is None else word_text.strip()
        new_meaning = row.meaning if meaning_text is None else normalize_meaning(meaning_text)
        problems = find_word_problems(new_word, new_meaning)
        if problems:
            raise _invalid_input(problems)
        new_key = new_word.lower()
        existing = word_repository.find_active_by_key(self.db, self.user_id, new_key)
        # 자기 자신의 대소문자만 바꾸는 수정은 허용한다 (D-24)
        if existing is not None and existing.id != row.id:
            raise _duplicate_error(existing.word)
        # id가 그대로이므로 학습 기록과 진도는 고칠 것이 없다 (D-W08)
        row.word, row.word_key, row.meaning = new_word, new_key, new_meaning
        try:
            self.db.commit()
        except IntegrityError:
            raise _duplicate_error(self._conflicting_word_text(new_key)) from None
        return row

    def delete_words(self, word_ids: list[int]) -> int:
        deleted_count = word_repository.soft_delete_words(
            self.db, self.user_id, word_ids, utc_now()
        )
        self.db.commit()
        return deleted_count

    def export_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_HEADER)
        for row in word_repository.list_all_active_words(self.db, self.user_id):
            writer.writerow(
                [csv_guard.neutralize_formula(row.word), csv_guard.neutralize_formula(row.meaning)]
            )
        return buffer.getvalue()

    def import_csv(self, raw: bytes, account_key_hash: str, ip_hash: str) -> ImportResult:
        now = utc_now()
        rate_limit.enforce_limit(
            self.db,
            rate_limit.IMPORT_PER_ACCOUNT,
            (rate_limit.ACTION_IMPORT,),
            now,
            account_key_hash=account_key_hash,
        )
        # 잘못된 파일로 반복 요청해도 횟수에 들어가도록 내용을 읽기 전에 기록한다
        auth_repository.add_attempt(
            self.db, account_key_hash, ip_hash, rate_limit.ACTION_IMPORT, now
        )
        self.db.commit()

        rows = self._read_rows(raw)
        result = ImportResult()
        existing_rows = word_repository.list_all_words_including_deleted(self.db, self.user_id)
        active_keys = {row.word_key for row in existing_rows if row.deleted_at is None}
        # 삭제 시각 오름차순이라 같은 키는 가장 최근에 지운 행이 사전에 남는다
        deleted_rows = {row.word_key: row for row in existing_rows if row.deleted_at is not None}
        for line_number, columns in rows:
            self._import_row(line_number, columns, result, active_keys, deleted_rows)
        try:
            self.db.commit()
        except IntegrityError:
            # 가져오는 중 같은 단어가 추가되면 전체를 되돌린다. 일부만 저장하지 않는다 (API 설계 §3)
            self.db.rollback()
            raise ApiError(
                409,
                "WORD_DUPLICATE",
                "가져오는 동안 단어장이 바뀌었습니다. 다시 시도해 주세요.",
            ) from None
        return result

    def _read_rows(self, raw: bytes) -> list[tuple[int, list[str]]]:
        if len(raw) > csv_guard.MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "파일은 5MB 이하여야 합니다.")
        text = csv_guard.decode_upload(raw)
        if text is None:
            raise _file_error("파일을 읽을 수 없습니다. UTF-8 또는 CP949 CSV 파일을 올려 주세요.")
        reader = csv.reader(io.StringIO(text, newline=""))
        rows: list[tuple[int, list[str]]] = []
        try:
            header = [column.strip() for column in next(reader, [])]
            if header != CSV_HEADER:
                raise _file_error(CSV_HEADER_ERROR)
            for columns in reader:
                if len(rows) >= csv_guard.MAX_IMPORT_ROWS:
                    raise ApiError(
                        413,
                        "FILE_TOO_LARGE",
                        f"파일은 {csv_guard.MAX_IMPORT_ROWS:,}행 이하여야 합니다.",
                    )
                rows.append((reader.line_num, columns))
        except csv.Error:
            raise _file_error(CSV_HEADER_ERROR) from None
        return rows

    def _import_row(
        self,
        line_number: int,
        columns: list[str],
        result: ImportResult,
        active_keys: set[str],
        deleted_rows: dict[str, Word],
    ) -> None:
        if not columns:
            return  # 빈 줄은 오류가 아니다
        if len(columns) < 2 or any(column.strip() for column in columns[2:]):
            self._record_invalid(result, line_number, "열은 word,meaning 두 개여야 합니다.")
            return
        word_text = csv_guard.restore_formula_prefix(columns[0].strip())
        meaning_text = normalize_meaning(csv_guard.restore_formula_prefix(columns[1].strip()))
        problems = find_word_problems(word_text, meaning_text)
        if problems:
            self._record_invalid(result, line_number, next(iter(problems.values())))
            return
        word_key = word_text.lower()
        if word_key in active_keys:
            result.skipped_duplicate += 1
            return
        active_keys.add(word_key)
        revived = deleted_rows.pop(word_key, None)
        if revived is not None:
            revived.word, revived.meaning, revived.deleted_at = word_text, meaning_text, None
        else:
            word_repository.add_word(self.db, self.user_id, word_text, word_key, meaning_text)
        result.added += 1

    @staticmethod
    def _record_invalid(result: ImportResult, line_number: int, reason: str) -> None:
        result.skipped_invalid += 1
        if len(result.invalid_rows) < MAX_REPORTED_INVALID_ROWS:
            result.invalid_rows.append({"row": line_number, "reason": reason})

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 회원이 공용 단어장을 담고 제외하는 규칙 (결정 D-WB02, D-WB03, D-WB06)
# 파일 위치: src/web/services/wordbook_service.py

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.db.base import utc_now
from web.db.tables import Wordbook
from web.errors import ApiError
from web.repositories import wordbook_repository, word_repository

SAMPLE_WORD_COUNT = 5
# 한 번에 지우는 단어 수. 쿼리 변수 개수 제한에 걸리지 않도록 나눈다
DELETE_CHUNK_SIZE = 500


@dataclass
class WordbookView:
    wordbook: Wordbook
    word_count: int
    sample_words: list[str]
    added: bool
    added_at: datetime | None


@dataclass
class AddResult:
    added: int  # 새로 담긴 단어 수
    already_had: int  # 이미 학습 중이라 건너뛴 단어 수


@dataclass
class RemoveResult:
    removed: int  # 학습에서 빠진 단어 수
    kept: int  # 다른 담은 단어장에도 있어 남긴 단어 수


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "단어장을 찾을 수 없습니다.")


class WordbookService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def list_wordbooks(self) -> list[WordbookView]:
        counts = wordbook_repository.count_entries_by_wordbook(self.db)
        samples = wordbook_repository.sample_words_by_wordbook(self.db, SAMPLE_WORD_COUNT)
        added_times = wordbook_repository.list_user_wordbook_times(self.db, self.user_id)
        return [
            WordbookView(
                wordbook=book,
                word_count=counts.get(book.id, 0),
                sample_words=samples.get(book.id, []),
                added=book.id in added_times,
                added_at=added_times.get(book.id),
            )
            for book in wordbook_repository.list_wordbooks(self.db)
        ]

    def add_wordbook(self, wordbook_id: int) -> AddResult:
        if wordbook_repository.get_wordbook(self.db, wordbook_id) is None:
            raise _not_found()
        entries = wordbook_repository.list_entries(self.db, wordbook_id)
        # 조회는 쓰기 전에 모두 끝낸다. 쓰는 중에 조회하면 자동 flush에서 제약 오류가 나 처리하기 어렵다
        already_added = wordbook_repository.has_user_wordbook(self.db, self.user_id, wordbook_id)
        existing_rows = word_repository.list_all_words_including_deleted(self.db, self.user_id)
        active_keys = {row.word_key for row in existing_rows if row.deleted_at is None}
        # 삭제 시각 오름차순이라 같은 키는 가장 최근에 지운 행이 사전에 남는다
        deleted_rows = {row.word_key: row for row in existing_rows if row.deleted_at is not None}
        result = AddResult(added=0, already_had=0)
        for entry in entries:
            if entry.word_key in active_keys:
                # 이미 학습 중인 단어는 뜻을 바꾸지 않는다 (D-WB06)
                result.already_had += 1
                continue
            active_keys.add(entry.word_key)
            revived = deleted_rows.pop(entry.word_key, None)
            if revived is not None:
                # 제외했던 단어를 다시 담으면 이전 학습 기록을 이어 간다 (FR-WORD-05)
                revived.word, revived.meaning, revived.deleted_at = entry.word, entry.meaning, None
            else:
                word_repository.add_word(
                    self.db, self.user_id, entry.word, entry.word_key, entry.meaning
                )
            result.added += 1
        if not already_added:
            wordbook_repository.add_user_wordbook(self.db, self.user_id, wordbook_id)
        try:
            self.db.commit()
        except IntegrityError:
            # 같은 회원이 동시에 담으면 유일 제약이 막는다. 일부만 저장하지 않고 전체를 되돌린다
            self.db.rollback()
            raise ApiError(
                409, "WORDBOOK_BUSY", "단어장을 담는 중 다른 요청이 있었습니다. 다시 시도해 주세요."
            ) from None
        return result

    def remove_wordbook(self, wordbook_id: int) -> RemoveResult:
        if wordbook_repository.get_wordbook(self.db, wordbook_id) is None:
            raise _not_found()
        if not wordbook_repository.has_user_wordbook(self.db, self.user_id, wordbook_id):
            return RemoveResult(removed=0, kept=0)  # 이미 제외한 단어장은 아무것도 바꾸지 않는다
        wordbook_repository.delete_user_wordbook(self.db, self.user_id, wordbook_id)
        book_keys = {
            entry.word_key for entry in wordbook_repository.list_entries(self.db, wordbook_id)
        }
        kept_keys = wordbook_repository.keys_in_other_added_wordbooks(
            self.db, self.user_id, wordbook_id
        )
        # 집합 연산은 행마다 다시 하지 않도록 반복문 밖에서 한 번만 한다
        removable_keys = book_keys - kept_keys
        shared_keys = book_keys & kept_keys
        active_rows = word_repository.list_all_active_words(self.db, self.user_id)
        removable_ids = [row.id for row in active_rows if row.word_key in removable_keys]
        kept_count = sum(1 for row in active_rows if row.word_key in shared_keys)
        now = utc_now()
        for start in range(0, len(removable_ids), DELETE_CHUNK_SIZE):
            chunk = removable_ids[start : start + DELETE_CHUNK_SIZE]
            word_repository.soft_delete_words(self.db, self.user_id, chunk, now)
        self.db.commit()
        return RemoveResult(removed=len(removable_ids), kept=kept_count)

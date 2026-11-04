#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원별 단어의 DB 읽기와 쓰기. 모든 쿼리에 user_id 조건을 건다 (D-A09)
# 파일 위치: src/web/repositories/word_repository.py

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from web.db.tables import PlanItem, Word

SORT_COLUMNS = {"word": Word.word_key, "meaning": Word.meaning, "created": Word.created_at}


def _active_words(user_id: int):
    return select(Word).where(Word.user_id == user_id, Word.deleted_at.is_(None))


def list_words(
    db: Session, user_id: int, keyword: str, sort: str, order: str, limit: int, offset: int
) -> tuple[list[Word], int]:
    statement = _active_words(user_id)
    if keyword:
        # autoescape가 없으면 사용자가 입력한 %와 _가 와일드카드로 동작한다
        statement = statement.where(
            or_(
                Word.word_key.contains(keyword, autoescape=True),
                func.lower(Word.meaning).contains(keyword, autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    column = SORT_COLUMNS[sort]
    sort_key = column.desc() if order == "desc" else column.asc()
    # 값이 같은 행의 순서가 흔들리면 페이지 사이에서 단어가 겹치거나 빠지므로 id를 함께 쓴다
    tie_break = Word.id.desc() if order == "desc" else Word.id.asc()
    items = db.scalars(statement.order_by(sort_key, tie_break).limit(limit).offset(offset)).all()
    return list(items), total


def list_all_active_words(db: Session, user_id: int) -> list[Word]:
    return list(db.scalars(_active_words(user_id).order_by(Word.id)))


def get_active_word(db: Session, user_id: int, word_id: int) -> Word | None:
    return db.scalar(_active_words(user_id).where(Word.id == word_id))


def find_active_by_key(db: Session, user_id: int, word_key: str) -> Word | None:
    return db.scalar(_active_words(user_id).where(Word.word_key == word_key))


def find_latest_deleted_by_key(db: Session, user_id: int, word_key: str) -> Word | None:
    # 삭제 후 이름 변경이 섞이면 같은 키의 삭제 행이 여럿일 수 있어 최근 것을 고른다
    return db.scalar(
        select(Word)
        .where(Word.user_id == user_id, Word.word_key == word_key, Word.deleted_at.is_not(None))
        .order_by(Word.deleted_at.desc(), Word.id.desc())
        .limit(1)
    )


def list_all_words_including_deleted(db: Session, user_id: int) -> list[Word]:
    return list(db.scalars(select(Word).where(Word.user_id == user_id).order_by(Word.deleted_at)))


def add_word(db: Session, user_id: int, word: str, word_key: str, meaning: str) -> Word:
    row = Word(user_id=user_id, word=word, word_key=word_key, meaning=meaning)
    db.add(row)
    return row


def soft_delete_words(db: Session, user_id: int, word_ids: Iterable[int], now: datetime) -> int:
    active_ids = list(
        db.scalars(
            select(Word.id).where(
                Word.user_id == user_id, Word.deleted_at.is_(None), Word.id.in_(list(word_ids))
            )
        )
    )
    if not active_ids:
        return 0
    # 지운 단어가 복습 후보로 다시 나오지 않게 진도에서는 뺀다. 학습 기록은 남긴다 (D-12, D-W07)
    db.execute(
        delete(PlanItem).where(PlanItem.user_id == user_id, PlanItem.word_id.in_(active_ids))
    )
    db.execute(
        update(Word)
        .where(Word.user_id == user_id, Word.id.in_(active_ids))
        .values(deleted_at=now, updated_at=now)
    )
    return len(active_ids)

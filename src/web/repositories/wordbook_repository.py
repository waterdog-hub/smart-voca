#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 공용 단어장과 회원이 담은 단어장의 DB 읽기와 쓰기 (결정 D-WB01)
# 파일 위치: src/web/repositories/wordbook_repository.py

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from web.db.tables import UserWordbook, Wordbook, WordbookEntry


def list_wordbooks(db: Session) -> list[Wordbook]:
    return list(db.scalars(select(Wordbook).order_by(Wordbook.id)))


def get_wordbook(db: Session, wordbook_id: int) -> Wordbook | None:
    return db.get(Wordbook, wordbook_id)


def find_by_slug(db: Session, slug: str) -> Wordbook | None:
    return db.scalar(select(Wordbook).where(Wordbook.slug == slug))


def count_entries_by_wordbook(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(WordbookEntry.wordbook_id, func.count()).group_by(WordbookEntry.wordbook_id)
    )
    return {wordbook_id: count for wordbook_id, count in rows}


def sample_words_by_wordbook(db: Session, sample_size: int) -> dict[int, list[str]]:
    # position은 1부터 시작하므로 앞쪽 몇 개만 한 번에 읽는다. 단어장마다 쿼리하지 않는다
    rows = db.execute(
        select(WordbookEntry.wordbook_id, WordbookEntry.word)
        .where(WordbookEntry.position <= sample_size)
        .order_by(WordbookEntry.wordbook_id, WordbookEntry.position)
    )
    samples: dict[int, list[str]] = {}
    for wordbook_id, word in rows:
        samples.setdefault(wordbook_id, []).append(word)
    return samples


def list_entries(db: Session, wordbook_id: int) -> list[WordbookEntry]:
    return list(
        db.scalars(
            select(WordbookEntry)
            .where(WordbookEntry.wordbook_id == wordbook_id)
            .order_by(WordbookEntry.position)
        )
    )


def replace_entries(db: Session, wordbook_id: int, rows: Iterable[tuple[str, str, str]]) -> int:
    """단어장 항목을 통째로 바꾼다. rows는 (단어, 단어 키, 뜻)이고 순서가 position이 된다."""
    db.execute(delete(WordbookEntry).where(WordbookEntry.wordbook_id == wordbook_id))
    count = 0
    for count, (word, word_key, meaning) in enumerate(rows, start=1):
        db.add(
            WordbookEntry(
                wordbook_id=wordbook_id,
                word=word,
                word_key=word_key,
                meaning=meaning,
                position=count,
            )
        )
    return count


def list_user_wordbook_times(db: Session, user_id: int) -> dict[int, datetime]:
    rows = db.execute(
        select(UserWordbook.wordbook_id, UserWordbook.added_at).where(
            UserWordbook.user_id == user_id
        )
    )
    return {wordbook_id: added_at for wordbook_id, added_at in rows}


def has_user_wordbook(db: Session, user_id: int, wordbook_id: int) -> bool:
    return db.get(UserWordbook, (user_id, wordbook_id)) is not None


def add_user_wordbook(db: Session, user_id: int, wordbook_id: int) -> None:
    db.add(UserWordbook(user_id=user_id, wordbook_id=wordbook_id))


def delete_user_wordbook(db: Session, user_id: int, wordbook_id: int) -> None:
    db.execute(
        delete(UserWordbook).where(
            UserWordbook.user_id == user_id, UserWordbook.wordbook_id == wordbook_id
        )
    )


def keys_in_other_added_wordbooks(db: Session, user_id: int, wordbook_id: int) -> set[str]:
    """회원이 담은 다른 단어장에 들어 있는 단어 키. 제외할 때 지우지 않고 남길 단어를 가린다."""
    rows = db.scalars(
        select(WordbookEntry.word_key)
        .join(UserWordbook, UserWordbook.wordbook_id == WordbookEntry.wordbook_id)
        .where(UserWordbook.user_id == user_id, UserWordbook.wordbook_id != wordbook_id)
    )
    return set(rows)

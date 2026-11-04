#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원별 일차 진도와 암기 기록의 DB 읽기와 쓰기. 모든 쿼리에 user_id 조건을 건다 (D-A09)
# 파일 위치: src/web/repositories/plan_repository.py

from datetime import date

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from web.db.tables import PlanItem, StudyRecord, UserSetting, Word


def list_day_summaries(db: Session, user_id: int) -> list[tuple[int, int, int]]:
    """(일차, 단어 수, 완료 수) 목록을 일차 순으로 돌려준다."""
    done_count = func.sum(case((PlanItem.done.is_(True), 1), else_=0))
    rows = db.execute(
        select(PlanItem.day, func.count(), done_count)
        .where(PlanItem.user_id == user_id)
        .group_by(PlanItem.day)
        .order_by(PlanItem.day)
    )
    return [(day, total, int(done)) for day, total, done in rows]


def list_day_items(db: Session, user_id: int, day: int) -> list[tuple[PlanItem, Word]]:
    rows = db.execute(
        select(PlanItem, Word)
        .join(Word, PlanItem.word_id == Word.id)
        .where(PlanItem.user_id == user_id, PlanItem.day == day)
        # "다시"가 겹친 순서를 만들어도 화면 순서가 흔들리지 않게 id를 함께 쓴다
        .order_by(PlanItem.position, PlanItem.id)
    )
    return [(item, word) for item, word in rows]


def find_item(db: Session, user_id: int, item_id: int) -> tuple[PlanItem, Word] | None:
    row = db.execute(
        select(PlanItem, Word)
        .join(Word, PlanItem.word_id == Word.id)
        .where(PlanItem.user_id == user_id, PlanItem.id == item_id)
    ).first()
    return (row[0], row[1]) if row else None


def raise_current_day(db: Session, user_id: int, expected_day: int) -> bool:
    """일차가 아직 expected_day일 때만 하나 올린다. 동시 요청 중 한쪽만 성공한다 (API 설계 §5)."""
    result = db.execute(
        update(UserSetting)
        .where(UserSetting.user_id == user_id, UserSetting.current_day == expected_day)
        .values(current_day=expected_day + 1)
    )
    return result.rowcount == 1


def mark_done(db: Session, user_id: int, item_id: int) -> bool:
    """아직 완료가 아닌 항목만 완료로 바꾼다. 실제로 바꿨을 때만 True다 (D-API05)."""
    result = db.execute(
        update(PlanItem)
        .where(PlanItem.user_id == user_id, PlanItem.id == item_id, PlanItem.done.is_(False))
        .values(done=True)
    )
    return result.rowcount == 1


def next_position(db: Session, user_id: int, day: int) -> int:
    last = db.scalar(
        select(func.max(PlanItem.position)).where(PlanItem.user_id == user_id, PlanItem.day == day)
    )
    return (last or 0) + 1


def add_memorized(db: Session, user_id: int, word_id: int, day: int, today: date) -> None:
    record = db.get(StudyRecord, (user_id, word_id))
    if record is None:
        record = StudyRecord(user_id=user_id, word_id=word_id)
        db.add(record)
        db.flush()
    record.memorized_count = StudyRecord.memorized_count + 1
    if record.first_memorized_day == 0:
        record.first_memorized_day = day
    record.last_memorized_date = today


def load_records(db: Session, user_id: int) -> list[tuple[str, int, int]]:
    """살아 있는 단어의 (단어, 외운 횟수, 오답 횟수) 목록을 돌려준다."""
    rows = db.execute(
        select(Word.word, StudyRecord.memorized_count, StudyRecord.wrong_count)
        .join(StudyRecord, StudyRecord.word_id == Word.id)
        .where(Word.user_id == user_id, StudyRecord.user_id == user_id, Word.deleted_at.is_(None))
    )
    return [(word, memorized, wrong) for word, memorized, wrong in rows]


def count_active_words(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(Word).where(Word.user_id == user_id, Word.deleted_at.is_(None))
    )


def count_memorized_words(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(StudyRecord)
        .join(Word, StudyRecord.word_id == Word.id)
        .where(
            StudyRecord.user_id == user_id,
            StudyRecord.memorized_count >= 1,
            Word.deleted_at.is_(None),
        )
    )

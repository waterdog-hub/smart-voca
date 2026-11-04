#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원별 시험 세트, 문항, 결과, 오답 기록의 DB 읽기와 쓰기 (D-A09)
# 파일 위치: src/web/repositories/test_repository.py

from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from web.db.tables import StudyRecord, TestAttempt, TestAttemptItem, TestSession


def find_attempt(db: Session, user_id: int, attempt_id: int) -> TestAttempt | None:
    return db.scalar(
        select(TestAttempt).where(TestAttempt.user_id == user_id, TestAttempt.id == attempt_id)
    )


def find_open_attempt(db: Session, user_id: int, now: datetime) -> TestAttempt | None:
    return db.scalar(
        select(TestAttempt)
        .where(
            TestAttempt.user_id == user_id,
            TestAttempt.status == "open",
            TestAttempt.expires_at > now,
        )
        .order_by(TestAttempt.id.desc())
        .limit(1)
    )


def expire_open_attempts(db: Session, user_id: int) -> None:
    db.execute(
        update(TestAttempt)
        .where(TestAttempt.user_id == user_id, TestAttempt.status == "open")
        .values(status="expired")
    )


def list_items(db: Session, attempt_id: int) -> list[TestAttemptItem]:
    return list(
        db.scalars(
            select(TestAttemptItem)
            .where(TestAttemptItem.attempt_id == attempt_id)
            .order_by(TestAttemptItem.position)
        )
    )


def mark_submitted(db: Session, user_id: int, attempt_id: int, now: datetime) -> bool:
    """제출 가능한 시험만 제출로 바꾼다. 동시 요청 중 한쪽만 성공한다 (데이터 모델 §3.8)."""
    result = db.execute(
        update(TestAttempt)
        .where(
            TestAttempt.user_id == user_id,
            TestAttempt.id == attempt_id,
            TestAttempt.status == "open",
            TestAttempt.expires_at > now,
        )
        .values(status="submitted", submitted_at=now)
    )
    return result.rowcount == 1


def add_wrong(db: Session, user_id: int, word_id: int, today: date) -> None:
    record = db.get(StudyRecord, (user_id, word_id))
    if record is None:
        record = StudyRecord(user_id=user_id, word_id=word_id)
        db.add(record)
        db.flush()
    record.wrong_count = StudyRecord.wrong_count + 1
    record.last_wrong_date = today


def find_session_of_attempt(db: Session, user_id: int, attempt_id: int) -> TestSession | None:
    return db.scalar(
        select(TestSession).where(
            TestSession.user_id == user_id, TestSession.attempt_id == attempt_id
        )
    )


def list_sessions(db: Session, user_id: int, limit: int, offset: int) -> list[TestSession]:
    return list(
        db.scalars(
            select(TestSession)
            .where(TestSession.user_id == user_id)
            .order_by(TestSession.taken_at.desc(), TestSession.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def summarize_sessions(db: Session, user_id: int) -> tuple[int, int, int]:
    """(시험 횟수, 문항 합계, 정답 합계)를 돌려준다."""
    count, total, score = db.execute(
        select(func.count(), func.sum(TestSession.total), func.sum(TestSession.score)).where(
            TestSession.user_id == user_id
        )
    ).one()
    return count, total or 0, score or 0

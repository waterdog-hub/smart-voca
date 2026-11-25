#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-25 - smart-voca - 학습 통계에 쓰는 DB 조회. 모든 쿼리에 user_id 조건을 건다 (VOCA-FR-031~034)
# 파일 위치: src/web/repositories/stats_repository.py

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from web.db.tables import TestResult, TestSession, Word


def list_sessions_oldest_first(db: Session, user_id: int) -> list[TestSession]:
    return list(
        db.scalars(
            select(TestSession)
            .where(TestSession.user_id == user_id)
            .order_by(TestSession.taken_at, TestSession.id)
        )
    )


def list_most_wrong_words(db: Session, user_id: int, limit: int) -> list[tuple[Word, int, int]]:
    """(단어, 틀린 횟수, 출제 횟수)를 틀린 횟수가 많은 순서로 돌려준다. 지운 단어는 뺀다."""
    # 빈 칸으로 낸 문항은 오답 기록에 넣지 않는 기존 규칙(시험 서비스)과 맞춘다
    wrong_count = func.sum(
        case((and_(TestResult.is_correct.is_(False), TestResult.answered.is_(True)), 1), else_=0)
    )
    rows = db.execute(
        select(Word, wrong_count.label("wrong"), func.count(TestResult.id).label("asked"))
        .join(Word, Word.id == TestResult.word_id)
        .where(TestResult.user_id == user_id, Word.user_id == user_id, Word.deleted_at.is_(None))
        .group_by(Word.id)
        .having(wrong_count > 0)
        .order_by(wrong_count.desc(), Word.word_key)
        .limit(limit)
    ).all()
    return [(word, int(wrong), int(asked)) for word, wrong, asked in rows]

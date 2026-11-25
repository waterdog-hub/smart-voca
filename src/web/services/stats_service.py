#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-25 - smart-voca - 학습 진척 통계를 DB 이력으로 계산한다 (VOCA-FR-031~034)
# 파일 위치: src/web/services/stats_service.py
#
# 화면에 값을 직접 쓰지 않는다. 진도는 plan_items·study_records, 성적은 test_sessions,
# 자주 틀린 단어는 test_results 에서 계산한다 (VOCA-FR-034).

from collections import OrderedDict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from web.repositories import stats_repository
from web.services.plan_service import KOREA_TIME, PlanService, Progress
from web.services.test_service import accuracy_percent

TOP_WRONG_LIMIT = 10
RECENT_SESSION_LIMIT = 20


@dataclass
class SessionPoint:
    number: int  # 몇 번째 시험인지 (1부터)
    taken_at: str
    score: int
    total: int
    percent: int


@dataclass
class DayPoint:
    date: str  # 한국 날짜 YYYY-MM-DD
    tests: int
    score: int
    total: int
    percent: int


@dataclass
class WrongWord:
    word: str
    meaning: str
    wrong: int
    asked: int


@dataclass
class Stats:
    progress: Progress
    test_count: int
    overall_percent: int
    sessions: list[SessionPoint]  # 최근 회차, 오래된 것부터
    days: list[DayPoint]  # 날짜별, 오래된 것부터
    wrong_words: list[WrongWord]


class StatsService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def build(self) -> Stats:
        sessions = stats_repository.list_sessions_oldest_first(self.db, self.user_id)
        points = [
            SessionPoint(
                number=index,
                taken_at=session.taken_at.astimezone(KOREA_TIME).strftime("%m-%d %H:%M"),
                score=session.score,
                total=session.total,
                percent=accuracy_percent(session.score, session.total),
            )
            for index, session in enumerate(sessions, start=1)
        ]
        # 저장은 UTC, 날짜 묶음은 한국 날짜로 한다 (D-W11)
        by_day: OrderedDict[str, list[int]] = OrderedDict()
        for session in sessions:
            key = session.taken_at.astimezone(KOREA_TIME).strftime("%Y-%m-%d")
            tests, score, total = by_day.get(key, [0, 0, 0])
            by_day[key] = [tests + 1, score + session.score, total + session.total]
        days = [
            DayPoint(date=key, tests=tests, score=score, total=total, percent=accuracy_percent(score, total))
            for key, (tests, score, total) in by_day.items()
        ]
        total_score = sum(session.score for session in sessions)
        total_items = sum(session.total for session in sessions)
        wrong_words = [
            WrongWord(word=word.word, meaning=word.meaning, wrong=wrong, asked=asked)
            for word, wrong, asked in stats_repository.list_most_wrong_words(
                self.db, self.user_id, TOP_WRONG_LIMIT
            )
        ]
        return Stats(
            progress=PlanService(self.db, self.user_id).progress(),
            test_count=len(sessions),
            overall_percent=accuracy_percent(total_score, total_items),
            sessions=points[-RECENT_SESSION_LIMIT:],
            days=days,
            wrong_words=wrong_words,
        )

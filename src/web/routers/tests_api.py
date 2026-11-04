#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시험 시작, 문제 조회, 제출, 시험 기록 API (API 설계 §6)
# 파일 위치: src/web/routers/tests_api.py

from typing import Annotated

from fastapi import APIRouter, Path, Query

from web.db.tables import TestAttempt, TestAttemptItem
from web.dependencies import DbSession, LoggedIn, VerifiedWrite
from web.errors import ApiError
from web.schemas.common import MAX_DB_INT
from web.schemas.tests import (
    QuestionResponse,
    QuestionResultResponse,
    TestDetailResponse,
    TestHistoryItem,
    TestHistoryResponse,
    TestStartRequest,
    TestSubmitRequest,
    TestSubmitResponse,
)
from web.services.test_service import TestService, accuracy_percent, item_choices

router = APIRouter(prefix="/api/v1/tests", tags=["tests"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
PathId = Annotated[int, Path(ge=1, le=MAX_DB_INT)]


def _detail(attempt: TestAttempt, items: list[TestAttemptItem]) -> TestDetailResponse:
    return TestDetailResponse(
        id=attempt.id,
        test_format=attempt.test_format,
        test_direction=attempt.test_direction,
        expires_at=attempt.expires_at,
        items=[
            QuestionResponse(
                id=item.id,
                position=item.position,
                direction=item.direction,
                question=item.question,
                choices=item_choices(item),
            )
            for item in items
        ],
    )


@router.post("", status_code=201)
def start_test(payload: TestStartRequest, current: VerifiedWrite, db: DbSession) -> TestDetailResponse:
    service = TestService(db, current.user.id)
    attempt = service.start(payload.test_format, payload.test_direction, payload.count)
    return _detail(*service.get_open_attempt_items(attempt.id))


# 경로가 {attempt_id}와 겹치지 않도록 고정 경로를 앞에 둔다
@router.get("/history")
def test_history(
    current: LoggedIn,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0, le=MAX_DB_INT)] = 0,
) -> TestHistoryResponse:
    sessions, count, overall = TestService(db, current.user.id).history(limit, offset)
    return TestHistoryResponse(
        items=[
            TestHistoryItem(
                id=session.id,
                taken_at=session.taken_at,
                test_format=session.test_format,
                test_direction=session.test_direction,
                total=session.total,
                score=session.score,
                percent=accuracy_percent(session.score, session.total),
            )
            for session in sessions
        ],
        total_count=count,
        overall_percent=overall,
    )


@router.get("/{attempt_id}")
def get_test(attempt_id: PathId, current: LoggedIn, db: DbSession) -> TestDetailResponse:
    return _detail(*TestService(db, current.user.id).get_open_attempt_items(attempt_id))


@router.post("/{attempt_id}/submit")
def submit_test(
    attempt_id: PathId, payload: TestSubmitRequest, current: VerifiedWrite, db: DbSession
) -> TestSubmitResponse:
    answers = {entry.item_id: entry.answer for entry in payload.answers}
    if len(answers) != len(payload.answers):
        raise ApiError(400, "VALIDATION_FAILED", "같은 문항의 답을 두 번 보낼 수 없습니다.")
    result = TestService(db, current.user.id).submit(attempt_id, answers)
    return TestSubmitResponse(
        total=result.total,
        score=result.score,
        percent=accuracy_percent(result.score, result.total),
        items=[
            QuestionResultResponse(
                id=entry.item.id,
                position=entry.item.position,
                question=entry.item.question,
                correct=entry.correct,
                your_answer=entry.your_answer,
                correct_answer=entry.correct_answer,
            )
            for entry in result.results
        ],
    )

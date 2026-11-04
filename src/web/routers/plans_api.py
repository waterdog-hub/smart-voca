#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 일차 진도, 암기 처리, 진행률 API (API 설계 §5)
# 파일 위치: src/web/routers/plans_api.py

from typing import Annotated

from fastapi import APIRouter, Path

from web.db.tables import PlanItem, Word
from web.dependencies import DbSession, LoggedIn, VerifiedWrite
from web.schemas.common import MAX_DB_INT
from web.schemas.plans import (
    PlanCreatedResponse,
    PlanDaySummary,
    PlanDetailResponse,
    PlanItemResponse,
    PlanItemUpdateRequest,
    PlanListResponse,
    ProgressResponse,
)
from web.services.plan_service import PlanService

router = APIRouter(prefix="/api/v1", tags=["plans"])

PathId = Annotated[int, Path(ge=1, le=MAX_DB_INT)]


def _item_response(item: PlanItem, word: Word) -> PlanItemResponse:
    return PlanItemResponse(
        id=item.id,
        day=item.day,
        word=word.word,
        meaning=word.meaning,
        assigned_type=item.assigned_type,
        done=item.done,
        position=item.position,
    )


@router.get("/plans")
def list_plans(current: LoggedIn, db: DbSession) -> PlanListResponse:
    service = PlanService(db, current.user.id)
    return PlanListResponse(
        current_day=service.current_day(),
        items=[
            PlanDaySummary(day=day, total=total, done=done)
            for day, total, done in service.list_days()
        ],
    )


@router.post("/plans", status_code=201)
def create_plan(current: VerifiedWrite, db: DbSession) -> PlanCreatedResponse:
    service = PlanService(db, current.user.id)
    day = service.create_next_day()
    return PlanCreatedResponse(
        day=day, items=[_item_response(*row) for row in service.get_day_items(day)]
    )


@router.get("/plans/{day}")
def get_plan(day: PathId, current: LoggedIn, db: DbSession) -> PlanDetailResponse:
    service = PlanService(db, current.user.id)
    return PlanDetailResponse(
        day=day,
        is_current=day == service.current_day(),
        items=[_item_response(*row) for row in service.get_day_items(day)],
    )


@router.patch("/plan-items/{item_id}")
def update_plan_item(
    item_id: PathId, payload: PlanItemUpdateRequest, current: VerifiedWrite, db: DbSession
) -> PlanItemResponse:
    service = PlanService(db, current.user.id)
    update = service.mark_memorized if payload.done else service.move_to_end
    return _item_response(*update(item_id))


@router.get("/progress")
def get_progress(current: LoggedIn, db: DbSession) -> ProgressResponse:
    progress = PlanService(db, current.user.id).progress()
    return ProgressResponse(
        total_words=progress.total_words,
        memorized_words=progress.memorized_words,
        current_day=progress.current_day,
        day_total=progress.day_total,
        day_done=progress.day_done,
    )

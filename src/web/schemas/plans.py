#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 진도·암기 API의 요청과 응답 형식 (API 설계 §5)
# 파일 위치: src/web/schemas/plans.py

from typing import Self

from pydantic import BaseModel, ConfigDict, StrictBool, model_validator


class PlanItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # StrictBool은 1을 참으로 바꾸지 않는다. 잘못된 호출이 외움으로 기록되는 일을 막는다
    done: StrictBool | None = None
    later: StrictBool | None = None

    @model_validator(mode="after")
    def exactly_one_action(self) -> Self:
        # 둘 다 보내면 어느 쪽을 뜻하는지 알 수 없다. false는 되돌리기처럼 보이지만 지원하지 않는다
        if {self.done, self.later} != {True, None}:
            raise ValueError("done 또는 later 중 하나만 true로 보내야 합니다.")
        return self


class PlanItemResponse(BaseModel):
    id: int
    day: int
    word: str
    meaning: str
    assigned_type: str
    done: bool
    position: int


class PlanDetailResponse(BaseModel):
    day: int
    is_current: bool
    items: list[PlanItemResponse]


class PlanDaySummary(BaseModel):
    day: int
    total: int
    done: int


class PlanListResponse(BaseModel):
    current_day: int
    items: list[PlanDaySummary]


class PlanCreatedResponse(BaseModel):
    day: int
    items: list[PlanItemResponse]


class ProgressResponse(BaseModel):
    total_words: int
    memorized_words: int
    current_day: int
    day_total: int
    day_done: int

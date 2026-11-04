#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시험 API의 요청과 응답 형식. 문항 응답에는 정답이 들어가지 않는다 (D-API02)
# 파일 위치: src/web/schemas/tests.py

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from web.schemas.common import DbInt

# 값의 범위와 한글 안내는 서비스에서 처리한다. 여기서는 형식과 과도한 길이만 막는다
MAX_CHOICE_LENGTH = 20
MAX_ANSWER_LENGTH = 500
MAX_ANSWERS = 200

ChoiceText = Annotated[str, Field(max_length=MAX_CHOICE_LENGTH)]


class TestStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_format: ChoiceText
    test_direction: ChoiceText
    count: StrictInt


class QuestionResponse(BaseModel):
    # word, answers, correct_index는 넣지 않는다. 뜻→영어 문항에서는 word가 곧 정답이다
    id: int
    position: int
    direction: str
    question: str
    choices: list[str]


class TestDetailResponse(BaseModel):
    id: int
    test_format: str
    test_direction: str
    expires_at: datetime
    items: list[QuestionResponse]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: DbInt
    # StrictInt는 true를 1번 보기로 바꾸지 않는다. 객관식은 보기 번호, 주관식은 글자다
    answer: StrictInt | Annotated[StrictStr, Field(max_length=MAX_ANSWER_LENGTH)]


class TestSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerRequest] = Field(max_length=MAX_ANSWERS)


class QuestionResultResponse(BaseModel):
    id: int
    position: int
    question: str
    correct: bool
    your_answer: str | None
    correct_answer: str


class TestSubmitResponse(BaseModel):
    total: int
    score: int
    percent: int
    items: list[QuestionResultResponse]


class TestHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    taken_at: datetime
    test_format: str
    test_direction: str
    total: int
    score: int
    percent: int


class TestHistoryResponse(BaseModel):
    items: list[TestHistoryItem]
    total_count: int
    overall_percent: int

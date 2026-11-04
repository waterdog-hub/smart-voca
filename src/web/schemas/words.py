#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 단어장 API의 요청과 응답 형식
# 파일 위치: src/web/schemas/words.py

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from web.schemas.common import DbInt

# 칸별 규칙과 한글 안내는 서비스에서 처리한다. 여기서는 형식과 과도한 길이만 막는다
MAX_REQUEST_TEXT_LENGTH = 2000
MAX_DELETE_IDS = 1000

RequestText = Annotated[str, Field(max_length=MAX_REQUEST_TEXT_LENGTH)]


class WordCreateRequest(BaseModel):
    word: RequestText
    meaning: RequestText


class WordUpdateRequest(BaseModel):
    word: RequestText | None = None
    meaning: RequestText | None = None


class WordDeleteRequest(BaseModel):
    ids: list[DbInt] = Field(min_length=1, max_length=MAX_DELETE_IDS)


class WordItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str
    meaning: str
    created_at: datetime


class WordListResponse(BaseModel):
    items: list[WordItem]
    total: int


class WordDeleteResponse(BaseModel):
    deleted: int


class ImportInvalidRow(BaseModel):
    row: int
    reason: str


class WordImportResponse(BaseModel):
    added: int
    skipped_duplicate: int
    skipped_invalid: int
    invalid_rows: list[ImportInvalidRow]

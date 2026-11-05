#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 내 단어 조회 API. 쓰기는 단어장 API로 옮겼다 (결정 D-WB04)
# 파일 위치: src/web/routers/words_api.py

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from web.dependencies import DbSession, LoggedIn
from web.schemas.common import MAX_DB_INT
from web.schemas.words import WordItem, WordListResponse
from web.services.word_service_web import WebWordService

router = APIRouter(prefix="/api/v1/words", tags=["words"])

MAX_KEYWORD_LENGTH = 100
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


@router.get("")
def list_words(
    current: LoggedIn,
    db: DbSession,
    q: Annotated[str, Query(max_length=MAX_KEYWORD_LENGTH)] = "",
    sort: Literal["word", "meaning", "created"] = "word",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0, le=MAX_DB_INT)] = 0,
) -> WordListResponse:
    items, total = WebWordService(db, current.user.id).list_words(q, sort, order, limit, offset)
    return WordListResponse(items=[WordItem.model_validate(item) for item in items], total=total)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 내 단어 조회·직접 등록·수정·삭제·CSV 가져오기 API (VOCA-FR-001~004)
# 파일 위치: src/web/routers/words_api.py

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Response, UploadFile

from web.dependencies import DbSession, LoggedIn, VerifiedWrite
from web.errors import ApiError
from web.schemas.common import MAX_DB_INT
from web.schemas.words import WordImportResponse, WordItem, WordListResponse, WordWriteRequest
from web.security import csv_guard
from web.services.word_service_web import WebWordService

router = APIRouter(prefix="/api/v1/words", tags=["words"])

MAX_KEYWORD_LENGTH = 100
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
WordId = Annotated[int, Path(ge=1, le=MAX_DB_INT)]


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


@router.post("", status_code=201)
def add_word(body: WordWriteRequest, current: VerifiedWrite, db: DbSession) -> WordItem:
    row = WebWordService(db, current.user.id).add_word(body.word, body.meaning)
    return WordItem.model_validate(row)


@router.put("/{word_id}")
def update_word(
    word_id: WordId, body: WordWriteRequest, current: VerifiedWrite, db: DbSession
) -> WordItem:
    row = WebWordService(db, current.user.id).update_word(word_id, body.word, body.meaning)
    return WordItem.model_validate(row)


@router.delete("/{word_id}", status_code=204)
def delete_word(word_id: WordId, current: VerifiedWrite, db: DbSession) -> Response:
    WebWordService(db, current.user.id).delete_word(word_id)
    return Response(status_code=204)


@router.post("/import")
async def import_words(file: UploadFile, current: VerifiedWrite, db: DbSession) -> WordImportResponse:
    # 크기 제한보다 1바이트 더 읽어 넘치는지만 확인한다. 파일은 메모리에서만 다룬다
    raw = await file.read(csv_guard.MAX_UPLOAD_BYTES + 1)
    if len(raw) > csv_guard.MAX_UPLOAD_BYTES:
        raise ApiError(413, "CSV_TOO_LARGE", "파일은 5MB 이하여야 합니다.")
    result = WebWordService(db, current.user.id).import_csv(raw)
    return WordImportResponse(
        added=result.added,
        skipped_existing=result.skipped_existing,
        skipped_duplicate=result.skipped_duplicate,
        invalid_count=result.invalid_count,
        problems=result.problems,
    )

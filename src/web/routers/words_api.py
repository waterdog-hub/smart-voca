#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 단어 조회, 추가, 수정, 삭제, CSV 가져오기·내보내기 API (API 설계 §3)
# 파일 위치: src/web/routers/words_api.py

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request, Response, UploadFile

from web.dependencies import DbSession, LoggedIn, VerifiedWrite, get_client_ip
from web.schemas.common import MAX_DB_INT
from web.schemas.words import (
    WordCreateRequest,
    WordDeleteRequest,
    WordDeleteResponse,
    WordImportResponse,
    WordItem,
    WordListResponse,
    WordUpdateRequest,
)
from web.security.csv_guard import MAX_UPLOAD_BYTES
from web.security.tokens import keyed_hash
from web.services.word_service_web import WebWordService

router = APIRouter(prefix="/api/v1/words", tags=["words"])

CSV_BOM = "﻿"  # Excel에서 한글이 깨지지 않게 한다 (D-01)
EXPORT_FILE_NAME = "smart-voca-words.csv"
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


@router.post("", status_code=201)
def add_word(payload: WordCreateRequest, current: VerifiedWrite, db: DbSession) -> WordItem:
    row = WebWordService(db, current.user.id).add_word(payload.word, payload.meaning)
    return WordItem.model_validate(row)


# 경로가 {word_id}와 겹치지 않도록 고정 경로를 앞에 둔다
@router.post("/delete")
def delete_words(
    payload: WordDeleteRequest, current: VerifiedWrite, db: DbSession
) -> WordDeleteResponse:
    deleted = WebWordService(db, current.user.id).delete_words(payload.ids)
    return WordDeleteResponse(deleted=deleted)


@router.post("/import")
def import_words(
    file: UploadFile, request: Request, current: VerifiedWrite, db: DbSession
) -> WordImportResponse:
    # 한 바이트 더 읽어 제한을 넘는지만 서비스가 확인한다. 큰 파일 전체를 메모리에 올리지 않는다
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    hash_key = request.app.state.settings.auth_hash_key
    result = WebWordService(db, current.user.id).import_csv(
        raw,
        account_key_hash=keyed_hash(hash_key, current.user.email),
        ip_hash=keyed_hash(hash_key, get_client_ip(request)),
    )
    return WordImportResponse(
        added=result.added,
        skipped_duplicate=result.skipped_duplicate,
        skipped_invalid=result.skipped_invalid,
        invalid_rows=result.invalid_rows,
    )


@router.get("/export")
def export_words(current: LoggedIn, db: DbSession) -> Response:
    content = CSV_BOM + WebWordService(db, current.user.id).export_csv()
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{EXPORT_FILE_NAME}"',
            # 회원의 단어장이 브라우저나 프록시에 남지 않게 한다
            "Cache-Control": "no-store",
        },
    )


@router.patch("/{word_id}")
def update_word(
    word_id: Annotated[int, Path(ge=1, le=MAX_DB_INT)],
    payload: WordUpdateRequest,
    current: VerifiedWrite,
    db: DbSession,
) -> WordItem:
    row = WebWordService(db, current.user.id).update_word(word_id, payload.word, payload.meaning)
    return WordItem.model_validate(row)

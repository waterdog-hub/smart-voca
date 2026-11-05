#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 공용 단어장 목록, 담기, 제외 API (결정 D-WB01~D-WB07)
# 파일 위치: src/web/routers/wordbooks_api.py

from typing import Annotated

from fastapi import APIRouter, Path

from web.dependencies import DbSession, LoggedIn, VerifiedWrite
from web.schemas.common import MAX_DB_INT
from web.schemas.wordbooks import (
    WordbookAddResponse,
    WordbookItem,
    WordbookListResponse,
    WordbookRemoveResponse,
)
from web.services.wordbook_service import WordbookService

router = APIRouter(prefix="/api/v1/wordbooks", tags=["wordbooks"])

WordbookId = Annotated[int, Path(ge=1, le=MAX_DB_INT)]


@router.get("")
def list_wordbooks(current: LoggedIn, db: DbSession) -> WordbookListResponse:
    views = WordbookService(db, current.user.id).list_wordbooks()
    return WordbookListResponse(
        items=[
            WordbookItem(
                id=view.wordbook.id,
                title=view.wordbook.title,
                description=view.wordbook.description,
                source_note=view.wordbook.source_note,
                word_count=view.word_count,
                sample_words=view.sample_words,
                added=view.added,
                added_at=view.added_at,
            )
            for view in views
        ]
    )


@router.post("/{wordbook_id}/add")
def add_wordbook(
    wordbook_id: WordbookId, current: VerifiedWrite, db: DbSession
) -> WordbookAddResponse:
    result = WordbookService(db, current.user.id).add_wordbook(wordbook_id)
    return WordbookAddResponse(added=result.added, already_had=result.already_had)


@router.post("/{wordbook_id}/remove")
def remove_wordbook(
    wordbook_id: WordbookId, current: VerifiedWrite, db: DbSession
) -> WordbookRemoveResponse:
    result = WordbookService(db, current.user.id).remove_wordbook(wordbook_id)
    return WordbookRemoveResponse(removed=result.removed, kept=result.kept)

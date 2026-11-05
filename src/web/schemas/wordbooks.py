#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 공용 단어장 API의 응답 형식
# 파일 위치: src/web/schemas/wordbooks.py

from datetime import datetime

from pydantic import BaseModel


class WordbookItem(BaseModel):
    id: int
    title: str
    description: str
    source_note: str
    word_count: int
    sample_words: list[str]
    added: bool
    added_at: datetime | None


class WordbookListResponse(BaseModel):
    items: list[WordbookItem]


class WordbookAddResponse(BaseModel):
    added: int
    already_had: int


class WordbookRemoveResponse(BaseModel):
    removed: int
    kept: int

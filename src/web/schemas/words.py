#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 내 단어 조회·등록·수정·CSV 가져오기 API의 요청과 응답 형식
# 파일 위치: src/web/schemas/words.py

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WordItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str
    meaning: str
    created_at: datetime


class WordListResponse(BaseModel):
    items: list[WordItem]
    total: int


class WordWriteRequest(BaseModel):
    # 길이와 글자 검사는 서비스(find_word_problems)가 한다. 여기서는 너무 긴 요청만 먼저 막는다
    word: str = Field(max_length=1000)
    meaning: str = Field(max_length=5000)


class WordImportResponse(BaseModel):
    added: int
    skipped_existing: int
    skipped_duplicate: int
    invalid_count: int
    problems: list[str]

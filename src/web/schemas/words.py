#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 내 단어 조회 API의 응답 형식
# 파일 위치: src/web/schemas/words.py

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WordItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str
    meaning: str
    created_at: datetime


class WordListResponse(BaseModel):
    items: list[WordItem]
    total: int

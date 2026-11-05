#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 웹 내 단어 조회 규칙. 추가·수정·삭제는 단어장 담기·제외로 대체했다 (결정 D-WB04)
# 파일 위치: src/web/services/word_service_web.py

from sqlalchemy.orm import Session

from web.db.tables import Word
from web.repositories import word_repository


class WebWordService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def list_words(
        self, keyword: str, sort: str, order: str, limit: int, offset: int
    ) -> tuple[list[Word], int]:
        needle = keyword.strip().lower()
        return word_repository.list_words(self.db, self.user_id, needle, sort, order, limit, offset)

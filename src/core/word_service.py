#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 단어 추가·수정·삭제 규칙과 검색 (WordService)
# 파일 위치: src/core/word_service.py
from typing import Dict, List, Optional, Set

from models import DayPlanItem, StudyRecord, Word


class WordService:
    """단어장 편집 규칙 모음. 화면은 이 클래스를 부르고, 파일 저장은 호출자가 한다.
    단어를 고치거나 지울 때 진도(day_plan)와 기록(study_record)도 함께 맞춘다 (설계 D-12, D-13).
    """

    @staticmethod
    def split_meanings(meaning_text: str) -> List[str]:
        """'달리다/운영하다' 같은 입력을 뜻 목록으로 나눈다."""
        return [item.strip() for item in meaning_text.split("/") if item.strip()]

    @staticmethod
    def validate(word_text: str, meaning_text: str, words: List[Word], editing_word: Optional[str] = None) -> str:
        """입력값 오류 메시지를 돌려준다. 문제가 없으면 빈 문자열이다.
        editing_word는 지금 고치는 단어 이름이다. 자기 자신과의 중복은 허용한다.
        대소문자만 다른 단어(Apple, apple)는 같은 단어로 본다 (설계 D-24).
        """
        if not word_text or not meaning_text:
            return "단어와 뜻을 모두 입력하세요."
        for word in words:
            if word.word != editing_word and word.word.lower() == word_text.lower():
                return f"이미 있는 단어입니다: {word.word}"
        return ""

    @staticmethod
    def filter_by_keyword(words: List[Word], keyword: str) -> List[Word]:
        """단어 또는 뜻에 keyword가 들어 있는 단어만 고른다. 대소문자는 구분하지 않는다."""
        needle = keyword.strip().lower()
        if not needle:
            return list(words)
        return [
            word for word in words
            if needle in word.word.lower() or needle in word.meaning_text.lower()
        ]

    @staticmethod
    def update_word(
        old_word: str,
        new_word: str,
        meaning_list: List[str],
        words: List[Word],
        records: Dict[str, StudyRecord],
        plan_items: List[DayPlanItem],
    ) -> None:
        """단어와 뜻을 고친다. 단어 이름이 바뀌면 기록 키와 진도의 단어 이름도 함께 바꾼다."""
        target = next(word for word in words if word.word == old_word)
        target.word = new_word
        target.meaning_list = meaning_list
        if old_word == new_word:
            return
        record = records.pop(old_word, None)
        if record is not None:
            record.word = new_word
            records[new_word] = record
        for item in plan_items:
            if item.word == old_word:
                item.word = new_word

    @staticmethod
    def remove_words(
        word_texts: Set[str],
        words: List[Word],
        plan_items: List[DayPlanItem],
    ) -> None:
        """단어를 지운다. 모든 일차의 진도에서도 해당 단어를 뺀다.
        학습 기록(study_record)은 남긴다 (설계 T-01). 지운 단어가 복습 후보로 다시 뽑히지 않게 하려고 진도에서는 뺀다.
        """
        words[:] = [word for word in words if word.word not in word_texts]
        plan_items[:] = [item for item in plan_items if item.word not in word_texts]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 단어, 학습 기록, 일차 진도, 설정 데이터 클래스 정의
# 파일 위치: src/models.py

from dataclasses import dataclass, field
from typing import List


@dataclass
class Word:
    """단어장의 한 단어. 뜻이 여러 개면 meaning_list에 나눠 담는다."""
    word: str
    meaning_list: List[str] = field(default_factory=list)

    @property
    def meaning_text(self) -> str:
        """CSV 저장용 뜻 문자열 (예: 달리다/운영하다)"""
        return "/".join(self.meaning_list)


@dataclass
class StudyRecord:
    """단어 하나의 암기·오답 기록 (study_record.csv 한 행)"""
    word: str
    memorized_count: int = 0
    first_memorized_day: int = 0      # 0이면 아직 외우지 않음
    last_memorized_date: str = ""     # YYYY-MM-DD
    wrong_count: int = 0
    last_wrong_date: str = ""         # YYYY-MM-DD


@dataclass
class DayPlanItem:
    """일차별 진도의 한 항목 (day_plan.csv 한 행)"""
    day: int
    word: str
    assigned_type: str                # new / review / wrong
    done: bool = False


@dataclass
class Settings:
    """설정 한 벌 (settings.csv 내용)"""
    daily_new_count: int = 20
    daily_review_count: int = 5
    daily_wrong_count: int = 5
    wrong_threshold: int = 3
    test_format: str = "multiple"
    test_direction: str = "en_ko"
    current_day: int = 0


@dataclass
class QuizItem:
    """시험 문항 하나. choices는 객관식일 때만 채운다."""
    word: str
    question: str                     # 화면에 보여줄 문제 (영어 단어 또는 뜻)
    answers: List[str]                # 정답으로 인정할 목록
    direction: str                    # en_ko / ko_en
    choices: List[str] = field(default_factory=list)
    correct_index: int = -1           # 객관식 정답 보기 번호

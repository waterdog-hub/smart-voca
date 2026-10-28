#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 시험 답안 정답 판정 (AnswerChecker)
# 파일 위치: src/core/answer_checker.py

from typing import Union

from models import QuizItem


class AnswerChecker:
    """객관식은 보기 번호, 주관식은 입력 글자로 정답을 판정한다."""

    def check_answer(self, quiz_item: QuizItem, user_answer: Union[int, str]) -> bool:
        """정답이면 True.

        객관식(choices 있음): user_answer는 보기 번호(int)
        주관식: user_answer는 입력 글자(str). 앞뒤 공백과 대소문자를 무시한다.
        정답 목록 중 하나만 맞아도 정답이다.
        """
        if quiz_item.choices:
            return user_answer == quiz_item.correct_index

        normalized_input = str(user_answer).strip().lower()
        if not normalized_input:
            return False
        return any(
            normalized_input == answer.strip().lower()
            for answer in quiz_item.answers
        )

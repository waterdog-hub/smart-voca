#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 정답 판정 단위 테스트
# 파일 위치: tests/test_answer_checker.py

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.answer_checker import AnswerChecker  # noqa: E402
from models import QuizItem  # noqa: E402


class AnswerCheckerTest(unittest.TestCase):

    def setUp(self):
        self.checker = AnswerChecker()

    def test_subjective_ignores_case_and_surrounding_spaces(self):
        item = QuizItem(word="Apple", question="Apple", answers=["사과"], direction="en_ko")
        self.assertTrue(self.checker.check_answer(item, "  사과 "))

        item = QuizItem(word="apple", question="사과", answers=["apple"], direction="ko_en")
        self.assertTrue(self.checker.check_answer(item, "APPLE"))

    def test_subjective_accepts_any_one_of_multiple_meanings(self):
        item = QuizItem(word="run", question="run", answers=["달리다", "운영하다"], direction="en_ko")
        self.assertTrue(self.checker.check_answer(item, "운영하다"))
        self.assertFalse(self.checker.check_answer(item, "걷다"))

    def test_empty_subjective_answer_is_wrong(self):
        item = QuizItem(word="run", question="run", answers=["달리다"], direction="en_ko")
        self.assertFalse(self.checker.check_answer(item, "   "))

    def test_multiple_choice_compares_option_index(self):
        item = QuizItem(word="run", question="run", answers=["달리다"], direction="en_ko",
                        choices=["달리다", "걷다", "먹다", "자다"], correct_index=0)
        self.assertTrue(self.checker.check_answer(item, 0))
        self.assertFalse(self.checker.check_answer(item, 2))


if __name__ == "__main__":
    unittest.main()

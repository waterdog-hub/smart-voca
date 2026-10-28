#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 일차별 진도 생성 로직 단위 테스트
# 파일 위치: tests/test_day_planner.py

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.day_planner import DayPlanner  # noqa: E402
from models import DayPlanItem, Settings, StudyRecord, Word  # noqa: E402


def make_words(count):
    return [Word(word=f"word{index:02d}", meaning_list=[f"뜻{index:02d}"]) for index in range(count)]


class DayPlannerTest(unittest.TestCase):

    def setUp(self):
        self.planner = DayPlanner(rng=random.Random(1))
        self.settings = Settings()

    def test_first_day_has_only_new_words(self):
        words = make_words(25)
        plan = self.planner.create_next_day_plan(words, {}, [], self.settings)

        self.assertEqual(len(plan), 20)
        self.assertTrue(all(item.assigned_type == "new" for item in plan))
        self.assertTrue(all(item.day == 1 for item in plan))

    def test_second_day_adds_review_words_from_previous_day(self):
        words = make_words(25)
        previous_items = [DayPlanItem(1, word.word, "new", done=True) for word in words[:20]]
        records = {word.word: StudyRecord(word=word.word, memorized_count=1) for word in words[:20]}
        settings = Settings(current_day=1)

        plan = self.planner.create_next_day_plan(words, records, previous_items, settings)
        new_items = [item for item in plan if item.assigned_type == "new"]
        review_items = [item for item in plan if item.assigned_type == "review"]

        self.assertEqual([item.word for item in new_items], [f"word{i:02d}" for i in range(20, 25)])
        self.assertEqual(len(review_items), 5)
        previous_words = {item.word for item in previous_items}
        self.assertTrue(all(item.word in previous_words for item in review_items))
        self.assertEqual(len({item.word for item in plan}), len(plan))  # 중복 없음

    def test_wrong_words_need_threshold_and_sorted_by_count(self):
        words = make_words(30)
        records = {
            "word00": StudyRecord(word="word00", memorized_count=1, wrong_count=2),
            "word01": StudyRecord(word="word01", memorized_count=1, wrong_count=3),
            "word02": StudyRecord(word="word02", memorized_count=1, wrong_count=7),
            "word03": StudyRecord(word="word03", memorized_count=1, wrong_count=5),
        }
        settings = Settings(current_day=1, daily_new_count=0, daily_review_count=0)

        plan = self.planner.create_next_day_plan(words, records, [], settings)
        wrong_words = [item.word for item in plan if item.assigned_type == "wrong"]

        self.assertEqual(wrong_words, ["word02", "word03", "word01"])

    def test_after_all_memorized_fills_short_wrong_slots_with_review(self):
        words = make_words(12)
        records = {word.word: StudyRecord(word=word.word, memorized_count=1) for word in words}
        records["word00"].wrong_count = 4
        records["word01"].wrong_count = 3
        previous_items = [DayPlanItem(5, word.word, "new", done=True) for word in words[:10]]
        settings = Settings(current_day=5)

        plan = self.planner.create_next_day_plan(words, records, previous_items, settings)
        types = [item.assigned_type for item in plan]

        self.assertEqual(types.count("new"), 0)
        self.assertEqual(types.count("wrong"), 2)
        self.assertEqual(types.count("review"), 8)  # 복습 5 + 부족한 오답 칸 3

    def test_all_memorized_check(self):
        words = make_words(3)
        records = {word.word: StudyRecord(word=word.word, memorized_count=1) for word in words}
        self.assertTrue(self.planner.is_all_memorized(words, records))

        records["word02"].memorized_count = 0
        self.assertFalse(self.planner.is_all_memorized(words, records))

    def test_empty_word_list_returns_empty_plan(self):
        plan = self.planner.create_next_day_plan([], {}, [], self.settings)
        self.assertEqual(plan, [])


if __name__ == "__main__":
    unittest.main()

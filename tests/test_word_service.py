#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 단어 편집 규칙(검증·검색·수정·삭제)과 시험 기록 저장 단위 테스트
# 파일 위치: tests/test_word_service.py

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.test_history_repository import TestHistoryRepository, accuracy_percent  # noqa: E402
from core.word_service import WordService  # noqa: E402
from models import DayPlanItem, StudyRecord, TestHistory, Word  # noqa: E402


def make_words():
    return [
        Word(word="apple", meaning_list=["사과"]),
        Word(word="run", meaning_list=["달리다", "운영하다"]),
        Word(word="book", meaning_list=["책"]),
    ]


class WordServiceValidateTest(unittest.TestCase):
    def test_empty_word_or_meaning_is_rejected(self):
        self.assertTrue(WordService.validate("", "뜻", make_words()))
        self.assertTrue(WordService.validate("cat", "", make_words()))

    def test_duplicate_word_is_rejected(self):
        message = WordService.validate("apple", "사과", make_words())
        self.assertIn("이미 있는 단어", message)

    def test_editing_word_may_keep_its_own_name(self):
        self.assertEqual(WordService.validate("apple", "사과2", make_words(), editing_word="apple"), "")

    def test_renaming_to_other_existing_word_is_rejected(self):
        self.assertTrue(WordService.validate("run", "뜻", make_words(), editing_word="apple"))

    def test_split_meanings_ignores_blank_parts(self):
        self.assertEqual(WordService.split_meanings(" 달리다 / / 운영하다 "), ["달리다", "운영하다"])


class WordServiceFilterTest(unittest.TestCase):
    def test_empty_keyword_returns_all_words(self):
        self.assertEqual(len(WordService.filter_by_keyword(make_words(), "  ")), 3)

    def test_matches_word_or_meaning_ignoring_case(self):
        words = make_words()
        self.assertEqual([w.word for w in WordService.filter_by_keyword(words, "APP")], ["apple"])
        self.assertEqual([w.word for w in WordService.filter_by_keyword(words, "운영")], ["run"])


class WordServiceUpdateTest(unittest.TestCase):
    def test_rename_moves_record_and_plan_items(self):
        words = make_words()
        records = {"apple": StudyRecord(word="apple", wrong_count=2)}
        plan_items = [DayPlanItem(1, "apple", "new", done=True)]

        WordService.update_word("apple", "apples", ["사과들"], words, records, plan_items)

        self.assertEqual(words[0].word, "apples")
        self.assertEqual(words[0].meaning_list, ["사과들"])
        self.assertNotIn("apple", records)
        self.assertEqual(records["apples"].word, "apples")
        self.assertEqual(records["apples"].wrong_count, 2)
        self.assertEqual(plan_items[0].word, "apples")

    def test_meaning_only_change_keeps_records_and_plan(self):
        words = make_words()
        records = {"book": StudyRecord(word="book", memorized_count=1)}
        plan_items = [DayPlanItem(1, "book", "new")]

        WordService.update_word("book", "book", ["서적"], words, records, plan_items)

        self.assertEqual(words[2].meaning_list, ["서적"])
        self.assertEqual(records["book"].memorized_count, 1)
        self.assertEqual(plan_items[0].word, "book")


class WordServiceRemoveTest(unittest.TestCase):
    def test_removed_word_disappears_from_all_days_of_plan(self):
        words = make_words()
        plan_items = [
            DayPlanItem(1, "apple", "new", done=True),
            DayPlanItem(1, "run", "new"),
            DayPlanItem(2, "apple", "review"),
            DayPlanItem(2, "book", "new"),
        ]

        WordService.remove_words({"apple"}, words, plan_items)

        self.assertEqual([w.word for w in words], ["run", "book"])
        self.assertEqual([(item.day, item.word) for item in plan_items],
                         [(1, "run"), (2, "book")])

    def test_removing_nothing_keeps_everything(self):
        words = make_words()
        plan_items = [DayPlanItem(1, "run", "new")]

        WordService.remove_words(set(), words, plan_items)

        self.assertEqual(len(words), 3)
        self.assertEqual(len(plan_items), 1)


class TestHistoryRepositoryTest(unittest.TestCase):
    def test_round_trip_keeps_all_fields(self):
        entries = [
            TestHistory(taken_at="2026-10-28 09:30", test_format="multiple",
                        test_direction="both", total=10, score=7),
            TestHistory(taken_at="2026-10-28 10:05", test_format="subjective",
                        test_direction="ko_en", total=5, score=0),
        ]
        repository = TestHistoryRepository()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_history.csv"
            repository.save(entries, path)
            self.assertEqual(repository.load(path), entries)

    def test_missing_file_gives_empty_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(TestHistoryRepository().load(Path(temp_dir) / "none.csv"), [])


class AccuracyPercentTest(unittest.TestCase):
    def test_empty_history_is_zero(self):
        self.assertEqual(accuracy_percent([]), 0)

    def test_percent_is_weighted_by_question_count(self):
        entries = [
            TestHistory(taken_at="a", test_format="multiple", test_direction="en_ko", total=10, score=10),
            TestHistory(taken_at="b", test_format="multiple", test_direction="en_ko", total=30, score=0),
        ]
        self.assertEqual(accuracy_percent(entries), 25)


if __name__ == "__main__":
    unittest.main()

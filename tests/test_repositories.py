#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - CSV 저장소 읽기·쓰기 왕복 및 오류 처리 단위 테스트
# 파일 위치: tests/test_repositories.py

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import DEFAULT_SETTINGS  # noqa: E402
from core.plan_repository import PlanRepository  # noqa: E402
from core.record_repository import RecordRepository  # noqa: E402
from core.settings_repository import SettingsRepository  # noqa: E402
from core.word_repository import WordRepository  # noqa: E402
from models import DayPlanItem, Settings, StudyRecord, Word  # noqa: E402


class RepositoryTest(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_word_round_trip_keeps_multiple_meanings(self):
        path = self.dir / "words.csv"
        words = [Word("run", ["달리다", "운영하다"]), Word("apple", ["사과"])]
        WordRepository().save(words, path)

        loaded, skipped = WordRepository().load(path)
        self.assertEqual(skipped, 0)
        self.assertEqual(loaded, words)

    def test_word_load_skips_duplicates_and_empty_rows(self):
        path = self.dir / "words.csv"
        path.write_text("word,meaning\napple,사과\napple,능금\n,빈단어\nbook,\nbook,책\n", encoding="utf-8")

        loaded, skipped = WordRepository().load(path)
        self.assertEqual([word.word for word in loaded], ["apple", "book"])
        self.assertEqual(loaded[0].meaning_list, ["사과"])
        self.assertEqual(skipped, 3)

    def test_word_load_treats_case_only_difference_as_duplicate(self):
        path = self.dir / "words.csv"
        path.write_text("word,meaning\nApple,사과\napple,능금\n", encoding="utf-8")

        loaded, skipped = WordRepository().load(path)
        self.assertEqual([word.word for word in loaded], ["Apple"])
        self.assertEqual(skipped, 1)

    def test_word_load_rejects_wrong_header(self):
        path = self.dir / "words.csv"
        path.write_text("english,korean\napple,사과\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            WordRepository().load(path)

    def test_settings_missing_file_uses_defaults(self):
        settings, warnings = SettingsRepository().load(self.dir / "none.csv")
        self.assertEqual(settings, Settings(**DEFAULT_SETTINGS))
        self.assertEqual(warnings, [])

    def test_settings_invalid_values_fall_back_with_warning(self):
        path = self.dir / "settings.csv"
        path.write_text("key,value\ndaily_new_count,abc\ntest_direction,up\nwrong_threshold,4\n",
                        encoding="utf-8")

        settings, warnings = SettingsRepository().load(path)
        self.assertEqual(settings.daily_new_count, DEFAULT_SETTINGS["daily_new_count"])
        self.assertEqual(settings.test_direction, DEFAULT_SETTINGS["test_direction"])
        self.assertEqual(settings.wrong_threshold, 4)
        self.assertEqual(len(warnings), 2)

    def test_settings_round_trip(self):
        path = self.dir / "settings.csv"
        settings = Settings(daily_new_count=10, test_format="subjective", test_direction="both", current_day=3)
        SettingsRepository().save(settings, path)

        loaded, warnings = SettingsRepository().load(path)
        self.assertEqual(loaded, settings)
        self.assertEqual(warnings, [])

    def test_record_round_trip(self):
        path = self.dir / "study_record.csv"
        records = {
            "apple": StudyRecord("apple", memorized_count=2, first_memorized_day=1,
                                 last_memorized_date="2026-10-21", wrong_count=3,
                                 last_wrong_date="2026-10-21"),
        }
        RecordRepository().save(records, path)

        self.assertEqual(RecordRepository().load(path), records)

    def test_plan_round_trip(self):
        path = self.dir / "day_plan.csv"
        items = [DayPlanItem(1, "apple", "new", done=True), DayPlanItem(2, "book", "wrong", done=False)]
        PlanRepository().save(items, path)

        self.assertEqual(PlanRepository().load(path), items)


if __name__ == "__main__":
    unittest.main()

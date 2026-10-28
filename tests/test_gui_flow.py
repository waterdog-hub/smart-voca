#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 화면 흐름 단위 테스트 (임시 폴더, 대화상자 자동 응답)
# 파일 위치: tests/test_gui_flow.py

import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui.app_window as app_window  # noqa: E402
from core.word_repository import WordRepository  # noqa: E402
from gui.plan_view_dialog import PlanViewDialog  # noqa: E402
from gui.test_history_dialog import TestHistoryDialog  # noqa: E402
from models import TestHistory, Word  # noqa: E402

DIALOG_MODULES = ("app_window", "word_list_tab", "memorize_tab", "test_tab", "settings_tab", "word_edit_dialog")


class FakeEditDialog:
    """단어 수정 대화상자 대신 미리 정한 결과를 돌려준다."""
    result = None

    def __init__(self, *_args, **_kwargs):
        self.result = FakeEditDialog.result


class GuiFlowTest(unittest.TestCase):
    """실제 창을 띄워 주요 흐름을 점검한다. 데이터는 임시 폴더에만 저장한다."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        words = [Word(word=f"w{index:02d}", meaning_list=[f"뜻{index}"]) for index in range(30)]
        WordRepository().save(words, self.temp_dir / "words.csv")

        for name, filename in (
            ("WORDS_CSV_PATH", "words.csv"),
            ("SETTINGS_CSV_PATH", "settings.csv"),
            ("RECORD_CSV_PATH", "study_record.csv"),
            ("PLAN_CSV_PATH", "day_plan.csv"),
            ("TEST_HISTORY_CSV_PATH", "test_history.csv"),
        ):
            patcher = mock.patch.object(app_window, name, self.temp_dir / filename)
            patcher.start()
            self.addCleanup(patcher.stop)

        for module in DIALOG_MODULES:
            patcher = mock.patch(f"gui.{module}.messagebox")
            patcher.start()
            self.addCleanup(patcher.stop)

        try:
            self.app = app_window.AppWindow()
        except tk.TclError as error:
            self.skipTest(f"화면을 띄울 수 없는 환경입니다: {error}")
        self.addCleanup(self._destroy_app)

    def _destroy_app(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def _select_word_in_table(self, tab, word_text):
        tab.refresh()
        for item in tab.table.get_children():
            if tab.table.item(item, "values")[0] == word_text:
                tab.table.selection_set(item)
                return
        self.fail(f"표에서 단어를 찾지 못했습니다: {word_text}")

    def test_memorize_with_keys_updates_progress(self):
        self.app.memorize_tab.on_create_next_day()
        self.assertEqual(len(self.app.current_day_items()), 20)
        self.assertEqual(int(float(self.app.memorize_tab.progress["maximum"])), 20)

        self.app.memorize_tab.handle_key("Right")
        self.app.memorize_tab.handle_key("Right")
        self.app.memorize_tab.handle_key("Left")
        done_count = sum(1 for item in self.app.current_day_items() if item.done)
        self.assertEqual(done_count, 2)
        self.assertEqual(int(float(self.app.memorize_tab.progress["value"])), 2)

    def test_keys_are_ignored_while_typing_in_entry(self):
        self.app.memorize_tab.on_create_next_day()
        before = sum(1 for item in self.app.current_day_items() if item.done)

        event = mock.Mock(widget=self.app.word_list_tab.word_entry, keysym="Right")
        self.app._on_key_press(event)

        self.assertEqual(sum(1 for item in self.app.current_day_items() if item.done), before)

    def test_deleting_word_removes_it_from_plan(self):
        self.app.memorize_tab.on_create_next_day()
        target = next(item.word for item in self.app.current_day_items() if not item.done)

        self._select_word_in_table(self.app.word_list_tab, target)
        self.app.word_list_tab.on_delete()

        self.assertTrue(all(word.word != target for word in self.app.words))
        self.assertTrue(all(item.word != target for item in self.app.plan_items))
        self.assertIn(target, self.app.records)  # 학습 기록은 남긴다 (T-01)

    def test_editing_word_renames_record_and_plan(self):
        self.app.memorize_tab.on_create_next_day()
        FakeEditDialog.result = ("renamed", ["새뜻", "추가뜻"])

        with mock.patch("gui.word_list_tab.WordEditDialog", FakeEditDialog):
            self._select_word_in_table(self.app.word_list_tab, "w01")
            self.app.word_list_tab.on_edit()

        renamed = [word for word in self.app.words if word.word == "renamed"]
        self.assertEqual(len(renamed), 1)
        self.assertEqual(renamed[0].meaning_text, "새뜻/추가뜻")
        self.assertIn("renamed", self.app.records)
        self.assertNotIn("w01", [item.word for item in self.app.plan_items])

    def test_search_filters_and_sort_reverses_on_second_click(self):
        tab = self.app.word_list_tab
        tab.search_var.set("뜻1")
        self.assertIn("검색 결과", tab.count_label.cget("text"))

        tab.search_var.set("")
        tab.on_sort("word")
        tab.on_sort("word")
        rows = [tab.table.item(item, "values")[0] for item in tab.table.get_children()]
        self.assertEqual(rows, sorted(rows, reverse=True))

    def test_test_flow_saves_history(self):
        tab = self.app.test_tab
        tab.format_box.set("객관식")
        tab.direction_box.set("영→한")
        tab.count_spin.set(3)
        tab.on_start()

        for _ in range(3):
            tab.handle_key("1")
            tab.handle_key("Return")
            tab.handle_key("Return")

        self.assertEqual(tab.quiz, [])
        self.assertEqual(len(self.app.test_history), 1)
        self.assertEqual(self.app.test_history[0].total, 3)
        self.assertTrue((self.temp_dir / "test_history.csv").exists())

    def test_history_dialog_shows_summary(self):
        self.app.add_test_history(TestHistory("2026-10-28 09:00", "multiple", "en_ko", 10, 7))
        self.app.add_test_history(TestHistory("2026-10-28 10:00", "subjective", "both", 5, 2))

        dialog = TestHistoryDialog(self.app.test_tab, self.app)
        self.addCleanup(dialog.destroy)

        self.assertEqual(dialog.summary_label.cget("text"), "시험 2회 · 전체 정답률 60%")
        self.assertEqual(len(dialog.table.get_children()), 2)

    def test_plan_view_shows_first_day(self):
        self.app.memorize_tab.on_create_next_day()
        dialog = PlanViewDialog(self.app.memorize_tab, self.app)
        self.addCleanup(dialog.destroy)

        self.assertEqual(dialog.day_box.get(), "1")
        self.assertEqual(len(dialog.table.get_children()), 20)


if __name__ == "__main__":
    unittest.main()

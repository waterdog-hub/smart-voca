#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 메인 창, 데이터 로드·저장 허브, 탭 구성, 키 입력 전달 (AppWindow)
# 파일 위치: src/gui/app_window.py

import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Set

from config import BACKUP_DIR, PLAN_CSV_PATH, RECORD_CSV_PATH, SETTINGS_CSV_PATH, TEST_HISTORY_CSV_PATH, WORDS_CSV_PATH
from core.day_planner import DayPlanner
from core.file_utils import backup_file
from core.plan_repository import PlanRepository
from core.record_repository import RecordRepository
from core.settings_repository import SettingsRepository
from core.test_history_repository import TestHistoryRepository
from core.word_repository import WordRepository
from core.word_service import WordService
from gui.memorize_tab import MemorizeTab
from gui.settings_tab import SettingsTab
from gui.test_tab import TestTab
from gui.word_list_tab import WordListTab
from models import DayPlanItem, Settings, StudyRecord, TestHistory, Word

# 글자를 입력하는 칸에서는 단축키를 가로채지 않는다
TEXT_INPUT_WIDGETS = (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Text)


class AppWindow(tk.Tk):
    """프로그램 메인 창. 데이터를 들고 있다가 각 탭에 넘기고, 저장도 여기서 맡는다."""

    def __init__(self):
        super().__init__()
        self.title("smart-voca 단어장")
        self.geometry("860x600")
        self.minsize(680, 500)

        self.words: List[Word] = []
        self.records: dict = {}
        self.settings = Settings()
        self.plan_items: List[DayPlanItem] = []
        self.test_history: List[TestHistory] = []

        self._load_all()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.word_list_tab = WordListTab(notebook, self)
        self.memorize_tab = MemorizeTab(notebook, self)
        self.test_tab = TestTab(notebook, self)
        self.settings_tab = SettingsTab(notebook, self)

        notebook.add(self.word_list_tab, text="단어장")
        notebook.add(self.memorize_tab, text="암기")
        notebook.add(self.test_tab, text="시험")
        notebook.add(self.settings_tab, text="설정")

        self._notebook = notebook
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.bind_all("<KeyPress>", self._on_key_press)

    # ---------- 데이터 로드 ----------

    def _load_all(self) -> None:
        """실행 시 CSV 파일들을 읽는다. 파일이 없으면 빈 상태로 시작한다."""
        if WORDS_CSV_PATH.exists():
            try:
                self.words, skipped_count = WordRepository().load(WORDS_CSV_PATH)
                if skipped_count:
                    messagebox.showinfo("단어 불러오기", f"중복되거나 빈 행 {skipped_count}개를 건너뛰었습니다.")
            except ValueError as error:
                messagebox.showerror("단어 파일 오류", str(error))

        settings, warnings = SettingsRepository().load(SETTINGS_CSV_PATH)
        self.settings = settings
        if warnings:
            messagebox.showwarning("설정 값 확인", "\n".join(warnings))

        self.records = RecordRepository().load(RECORD_CSV_PATH)
        self.ensure_records_for_words()
        self.plan_items = PlanRepository().load(PLAN_CSV_PATH)
        self.test_history = TestHistoryRepository().load(TEST_HISTORY_CSV_PATH)

    def ensure_records_for_words(self) -> None:
        """단어장에 있는데 기록이 없는 단어에 빈 기록을 만든다."""
        for word in self.words:
            self.records.setdefault(word.word, StudyRecord(word=word.word))

    # ---------- 저장 ----------

    def save_words(self) -> None:
        WordRepository().save(self.words, WORDS_CSV_PATH)

    def save_settings(self) -> None:
        SettingsRepository().save(self.settings, SETTINGS_CSV_PATH)

    def save_records(self) -> None:
        RecordRepository().save(self.records, RECORD_CSV_PATH)

    def save_plan(self) -> None:
        PlanRepository().save(self.plan_items, PLAN_CSV_PATH)

    def save_test_history(self) -> None:
        TestHistoryRepository().save(self.test_history, TEST_HISTORY_CSV_PATH)

    def backup_words_file(self):
        """단어장 파일을 백업하고 백업 경로를 돌려준다. 파일이 없으면 None이다."""
        return backup_file(WORDS_CSV_PATH, BACKUP_DIR)

    # ---------- 단어 편집 ----------

    def update_word(self, old_word: str, new_word: str, meaning_list: List[str]) -> None:
        """단어 수정을 반영하고 단어·기록·진도 파일을 함께 저장한다."""
        WordService.update_word(old_word, new_word, meaning_list,
                                self.words, self.records, self.plan_items)
        self.ensure_records_for_words()
        self.save_words()
        self.save_records()
        self.save_plan()

    def delete_words(self, word_texts: Set[str]) -> None:
        """단어를 지우고 진도에서도 뺀다. 학습 기록은 남긴다 (설계 T-01)."""
        WordService.remove_words(word_texts, self.words, self.plan_items)
        self.save_words()
        self.save_plan()

    # ---------- 진도 ----------

    def current_day_items(self) -> List[DayPlanItem]:
        """현재 일차(settings.current_day)의 진도 항목들."""
        return [item for item in self.plan_items if item.day == self.settings.current_day]

    def is_all_memorized(self) -> bool:
        """단어장의 모든 단어를 한 번 이상 외웠으면 True다."""
        return DayPlanner().is_all_memorized(self.words, self.records)

    def is_current_day_complete(self) -> bool:
        """현재 일차 남은 단어가 없으면 True다. 항목이 비어 있어도 True다 (단어 삭제로 비었을 때 막히지 않게)."""
        return all(item.done for item in self.current_day_items())

    def create_next_day_plan(self) -> bool:
        """다음 일차 진도를 만들고 저장한다. 만들었으면 True."""
        new_items = DayPlanner().create_next_day_plan(
            self.words, self.records, self.current_day_items(), self.settings)
        if not new_items:
            return False

        self.plan_items.extend(new_items)
        self.settings.current_day += 1
        self.save_plan()
        self.save_settings()
        return True

    # ---------- 시험 기록 ----------

    def add_test_history(self, entry: TestHistory) -> None:
        self.test_history.append(entry)
        self.save_test_history()

    # ---------- 탭 전환과 키 입력 ----------

    def current_tab(self):
        return self._notebook.nametowidget(self._notebook.select())

    def _on_tab_changed(self, _event) -> None:
        """탭을 바꿀 때 해당 탭의 화면을 최신 데이터로 다시 그린다."""
        current_tab = self.current_tab()
        if hasattr(current_tab, "refresh"):
            current_tab.refresh()

    def _on_key_press(self, event) -> None:
        """키 입력을 현재 탭에 넘긴다. 대화상자가 떠 있거나 입력칸에 커서가 있으면 무시한다."""
        widget = event.widget
        if not isinstance(widget, tk.Misc) or widget.winfo_toplevel() is not self:
            return
        if isinstance(widget, TEXT_INPUT_WIDGETS):
            return
        handle_key = getattr(self.current_tab(), "handle_key", None)
        if handle_key is not None:
            handle_key(event.keysym)


if __name__ == "__main__":
    AppWindow().mainloop()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 시험 탭: 형식·방향 선택, 문항 풀이, 채점, 오답 기록 (TestTab)
# 파일 위치: src/gui/test_tab.py

import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk
from typing import List, Optional

from config import TEST_DIRECTION_LABELS, TEST_FORMAT_LABELS
from core.answer_checker import AnswerChecker
from core.quiz_builder import QuizBuilder
from gui.test_history_dialog import TestHistoryDialog
from models import QuizItem, TestHistory

DIRECTION_PROMPTS = {
    "en_ko": "다음 영어 단어의 뜻은?",
    "ko_en": "다음 뜻에 해당하는 영어 단어는?",
}


def _label_of(mapping: dict, code: str) -> str:
    """코드값에 맞는 화면 라벨을 찾는다 (예: en_ko → 영→한)."""
    for label, value in mapping.items():
        if value == code:
            return label
    return next(iter(mapping))


class TestTab(ttk.Frame):
    """시험 한 세트를 진행한다. 답을 제출할 때마다 오답을 바로 저장한다 (설계 D-06)."""

    def __init__(self, master, app):
        super().__init__(master, padding=12)
        self.app = app
        self.checker = AnswerChecker()
        self.quiz: List[QuizItem] = []
        self.index = 0
        self.score = 0
        self.wrong_words: List[str] = []
        self.answered = False

        controls = ttk.Frame(self)
        controls.pack(fill="x")
        ttk.Label(controls, text="형식").pack(side="left")
        self.format_box = ttk.Combobox(controls, values=list(TEST_FORMAT_LABELS), state="readonly", width=8)
        self.format_box.pack(side="left", padx=4)
        ttk.Label(controls, text="방향").pack(side="left")
        self.direction_box = ttk.Combobox(controls, values=list(TEST_DIRECTION_LABELS), state="readonly", width=8)
        self.direction_box.pack(side="left", padx=4)
        ttk.Label(controls, text="문항 수").pack(side="left")
        self.count_spin = ttk.Spinbox(controls, from_=1, to=200, width=5)
        self.count_spin.set(10)
        self.count_spin.pack(side="left", padx=4)
        ttk.Button(controls, text="시험 시작", command=self.on_start).pack(side="right")
        ttk.Button(controls, text="시험 기록", command=self.on_open_history).pack(side="right", padx=4)

        self.progress_label = ttk.Label(self, text="")
        self.progress_label.pack(fill="x", pady=(16, 4))
        self.progress_bar = ttk.Progressbar(self, maximum=1, value=0)
        self.progress_bar.pack(fill="x")
        self.prompt_label = ttk.Label(self, text="", font=("맑은 고딕", 12))
        self.prompt_label.pack(fill="x")
        self.question_label = ttk.Label(self, text="", font=("맑은 고딕", 24, "bold"))
        self.question_label.pack(pady=12)

        self.answer_frame = ttk.Frame(self)
        self.answer_frame.pack(fill="x")
        self.choice_var = tk.IntVar(value=-1)
        self.choice_buttons: List[ttk.Radiobutton] = []
        self.entry_var = tk.StringVar()
        self.answer_entry = ttk.Entry(self.answer_frame, textvariable=self.entry_var, font=("맑은 고딕", 14))
        self.answer_entry.bind("<Return>", lambda _event: self.on_submit())

        self.feedback_label = ttk.Label(self, text="", font=("맑은 고딕", 12), wraplength=660)
        self.feedback_label.pack(fill="x", pady=12)

        self.submit_button = ttk.Button(self, text="제출 (Enter)", command=self.on_submit)
        self.submit_button.pack(side="bottom", anchor="e")
        self.current_format = "multiple"
        self.current_direction = "en_ko"

        self.refresh()

    def refresh(self) -> None:
        """설정값을 콤보박스 기본값으로 넣는다. 시험 진행 중이면 건드리지 않는다."""
        if self.quiz:
            return
        self.format_box.set(_label_of(TEST_FORMAT_LABELS, self.app.settings.test_format))
        self.direction_box.set(_label_of(TEST_DIRECTION_LABELS, self.app.settings.test_direction))
        self._show_idle()

    def on_start(self) -> None:
        if not self.app.words:
            messagebox.showwarning("시험", "단어장에 단어가 없습니다.")
            return
        try:
            count = int(self.count_spin.get())
        except ValueError:
            messagebox.showwarning("시험", "문항 수는 숫자로 입력하세요.")
            return
        test_format = TEST_FORMAT_LABELS.get(self.format_box.get(), "multiple")
        test_direction = TEST_DIRECTION_LABELS.get(self.direction_box.get(), "en_ko")
        self.current_format = test_format
        self.current_direction = test_direction

        try:
            self.quiz = QuizBuilder().build_quiz(self.app.words, test_format, test_direction, max(count, 1))
        except ValueError as error:
            messagebox.showwarning("시험", str(error))
            return

        self.index = 0
        self.score = 0
        self.wrong_words = []
        self._show_question()

    def on_open_history(self) -> None:
        TestHistoryDialog(self, self.app)

    def on_submit(self) -> None:
        if not self.quiz:
            return
        if self.answered:
            self._go_next()
            return

        item = self.quiz[self.index]
        if item.choices:
            if self.choice_var.get() < 0:
                messagebox.showinfo("시험", "보기를 선택하세요.")
                return
            user_answer = self.choice_var.get()
        else:
            user_answer = self.entry_var.get()

        is_correct = self.checker.check_answer(item, user_answer)
        if is_correct:
            self.score += 1
            self.feedback_label.configure(text="정답입니다.")
        else:
            self.wrong_words.append(item.word)
            self._record_wrong(item.word)
            self.feedback_label.configure(text=f"틀렸습니다. 정답: {self._correct_text(item)}")

        self.answered = True
        self._set_inputs_enabled(False)
        self.submit_button.configure(text="다음 (Enter)" if self.index + 1 < len(self.quiz) else "결과 보기 (Enter)")

    def _go_next(self) -> None:
        self.index += 1
        if self.index < len(self.quiz):
            self._show_question()
        else:
            self._show_result()

    def _show_question(self) -> None:
        item = self.quiz[self.index]
        self.answered = False
        self.progress_label.configure(text=f"{self.index + 1} / {len(self.quiz)}  ·  정답 {self.score}")
        self.progress_bar.configure(maximum=len(self.quiz), value=self.index)
        self.prompt_label.configure(text=DIRECTION_PROMPTS.get(item.direction, ""))
        self.question_label.configure(text=item.question)
        self.feedback_label.configure(text="")
        self.submit_button.configure(text="제출 (Enter)", state="normal")

        self._clear_answer_widgets()
        if item.choices:
            self.choice_var.set(-1)
            for index, choice_text in enumerate(item.choices):
                button = ttk.Radiobutton(self.answer_frame, text=f"{index + 1}. {choice_text}",
                                         variable=self.choice_var, value=index)
                button.pack(anchor="w", pady=2)
                self.choice_buttons.append(button)
        else:
            self.entry_var.set("")
            self.answer_entry.pack(fill="x", padx=40)
            self.answer_entry.focus_set()
        self._set_inputs_enabled(True)

    def _show_result(self) -> None:
        total = len(self.quiz)
        self.quiz = []
        self.answered = False
        self._clear_answer_widgets()
        self.question_label.configure(text=f"정답 {self.score} / {total}")
        self.prompt_label.configure(text="시험이 끝났습니다.")
        self.progress_label.configure(text="")
        self.progress_bar.configure(maximum=max(total, 1), value=total)
        if self.wrong_words:
            self.feedback_label.configure(text="틀린 단어: " + ", ".join(self.wrong_words))
        else:
            self.feedback_label.configure(text="모두 맞혔습니다.")
        self.submit_button.configure(text="제출 (Enter)", state="disabled")
        self._save_history(total)

    def _save_history(self, total: int) -> None:
        """시험 결과를 test_history.csv에 남긴다."""
        self.app.add_test_history(TestHistory(
            taken_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            test_format=self.current_format,
            test_direction=self.current_direction,
            total=total,
            score=self.score,
        ))

    def _show_idle(self) -> None:
        self.prompt_label.configure(text="형식과 방향을 고르고 '시험 시작'을 누르세요.")
        self.question_label.configure(text="")
        self.progress_label.configure(text="")
        self.progress_bar.configure(maximum=1, value=0)
        self.feedback_label.configure(text="")
        self._clear_answer_widgets()
        self.submit_button.configure(state="disabled")

    def handle_key(self, keysym: str) -> None:
        """메인 창이 넘겨주는 키 입력. 객관식은 1~4로 고르고, Enter로 제출하거나 다음으로 넘어간다."""
        if not self.quiz:
            return
        if keysym in ("Return", "KP_Enter"):
            self.on_submit()
            return
        item = self.quiz[self.index]
        if self.answered or not item.choices:
            return
        if keysym in ("1", "2", "3", "4"):
            choice_index = int(keysym) - 1
            if choice_index < len(item.choices):
                self.choice_var.set(choice_index)

    def _record_wrong(self, word_text: str) -> None:
        """오답 횟수를 올리고 바로 저장한다."""
        record = self.app.records.get(word_text)
        if record is None:
            return
        record.wrong_count += 1
        record.last_wrong_date = date.today().isoformat()
        self.app.save_records()

    def _correct_text(self, item: QuizItem) -> str:
        if item.choices:
            return item.choices[item.correct_index]
        return "/".join(item.answers)

    def _clear_answer_widgets(self) -> None:
        for button in self.choice_buttons:
            button.destroy()
        self.choice_buttons = []
        self.answer_entry.pack_forget()

    def _set_inputs_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.choice_buttons:
            button.configure(state=state)
        self.answer_entry.configure(state=state)

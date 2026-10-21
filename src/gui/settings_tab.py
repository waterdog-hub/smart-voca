#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 설정 탭: 하루 진도 구성, 오답 기준, 시험 기본값 편집 (SettingsTab)
# 파일 위치: src/gui/settings_tab.py

import tkinter as tk
from tkinter import messagebox, ttk

from config import TEST_DIRECTION_LABELS, TEST_FORMAT_LABELS
from gui.test_tab import _label_of

COUNT_FIELDS = [
    ("daily_new_count", "하루 신규 단어 수", 0),
    ("daily_review_count", "하루 복습 단어 수", 0),
    ("daily_wrong_count", "하루 오답 단어 최대 수", 0),
    ("wrong_threshold", "오답 단어 기준 (이 횟수 이상)", 1),
]


class SettingsTab(ttk.Frame):
    """설정을 고치면 settings.csv에 저장한다. 이미 만든 일차 진도는 바뀌지 않는다."""

    def __init__(self, master, app):
        super().__init__(master, padding=16)
        self.app = app
        self.count_vars = {}

        form = ttk.Frame(self)
        form.pack(anchor="nw")
        for row, (key, label_text, _minimum) in enumerate(COUNT_FIELDS):
            ttk.Label(form, text=label_text).grid(row=row, column=0, sticky="w", pady=4)
            variable = tk.StringVar()
            self.count_vars[key] = variable
            ttk.Entry(form, textvariable=variable, width=8).grid(row=row, column=1, sticky="w", padx=8)

        row = len(COUNT_FIELDS)
        ttk.Label(form, text="시험 기본 형식").grid(row=row, column=0, sticky="w", pady=4)
        self.format_box = ttk.Combobox(form, values=list(TEST_FORMAT_LABELS), state="readonly", width=10)
        self.format_box.grid(row=row, column=1, sticky="w", padx=8)

        row += 1
        ttk.Label(form, text="시험 기본 방향").grid(row=row, column=0, sticky="w", pady=4)
        self.direction_box = ttk.Combobox(form, values=list(TEST_DIRECTION_LABELS), state="readonly", width=10)
        self.direction_box.grid(row=row, column=1, sticky="w", padx=8)

        row += 1
        ttk.Button(form, text="저장", command=self.on_save).grid(row=row, column=0, columnspan=2, pady=16, sticky="w")

        self.refresh()

    def refresh(self) -> None:
        """현재 설정값을 입력칸에 채운다."""
        for key, _label_text, _minimum in COUNT_FIELDS:
            self.count_vars[key].set(str(getattr(self.app.settings, key)))
        self.format_box.set(_label_of(TEST_FORMAT_LABELS, self.app.settings.test_format))
        self.direction_box.set(_label_of(TEST_DIRECTION_LABELS, self.app.settings.test_direction))

    def on_save(self) -> None:
        new_values = {}
        for key, label_text, minimum in COUNT_FIELDS:
            raw_text = self.count_vars[key].get().strip()
            try:
                number = int(raw_text)
            except ValueError:
                messagebox.showerror("설정 저장", f"{label_text}은(는) 숫자로 입력하세요.")
                return
            if number < minimum:
                messagebox.showerror("설정 저장", f"{label_text}은(는) {minimum} 이상이어야 합니다.")
                return
            new_values[key] = number

        settings = self.app.settings
        for key, number in new_values.items():
            setattr(settings, key, number)
        settings.test_format = TEST_FORMAT_LABELS.get(self.format_box.get(), settings.test_format)
        settings.test_direction = TEST_DIRECTION_LABELS.get(self.direction_box.get(), settings.test_direction)

        self.app.save_settings()
        messagebox.showinfo("설정 저장", "설정을 저장했습니다. 다음 일차 진도부터 적용됩니다.")

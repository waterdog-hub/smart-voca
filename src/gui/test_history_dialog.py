#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 시험 기록 보기 창: 날짜별 결과와 전체 정답률 (TestHistoryDialog)
# 파일 위치: src/gui/test_history_dialog.py
import tkinter as tk
from tkinter import ttk

from config import TEST_DIRECTION_LABELS, TEST_FORMAT_LABELS
from core.test_history_repository import accuracy_percent

# 설정값(영문 코드)을 화면 라벨로 바꾸는 대응표
FORMAT_TEXT = {code: label for label, code in TEST_FORMAT_LABELS.items()}
DIRECTION_TEXT = {code: label for label, code in TEST_DIRECTION_LABELS.items()}


class TestHistoryDialog(tk.Toplevel):
    """저장된 시험 기록을 최근 순으로 보여준다. 읽기 전용이다."""

    def __init__(self, master, app):
        super().__init__(master)
        self.title("시험 기록")
        self.transient(master)
        self.geometry("620x420")
        self.app = app

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        self.summary_label = ttk.Label(body, text="", font=("맑은 고딕", 11, "bold"))
        self.summary_label.pack(anchor="w", pady=(0, 8))

        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)
        columns = ("taken_at", "format", "direction", "total", "score", "percent")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for column, title, width in (("taken_at", "시각", 140), ("format", "형식", 70),
                                     ("direction", "방향", 80), ("total", "문항", 60),
                                     ("score", "정답", 60), ("percent", "정답률", 80)):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, anchor="center" if column != "taken_at" else "w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.refresh()
        self.bind("<Escape>", lambda _event: self.destroy())

    def refresh(self) -> None:
        self.table.delete(*self.table.get_children())
        entries = sorted(self.app.test_history, key=lambda entry: entry.taken_at, reverse=True)
        for entry in entries:
            percent = round(entry.score * 100 / entry.total) if entry.total else 0
            self.table.insert("", "end", values=(
                entry.taken_at,
                FORMAT_TEXT.get(entry.test_format, entry.test_format),
                DIRECTION_TEXT.get(entry.test_direction, entry.test_direction),
                entry.total,
                entry.score,
                f"{percent}%",
            ))
        if entries:
            self.summary_label.configure(text=f"시험 {len(entries)}회 · 전체 정답률 {accuracy_percent(entries)}%")
        else:
            self.summary_label.configure(text="아직 본 시험이 없습니다.")

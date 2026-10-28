#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 일차별 진도 보기 창 (지난 일차 확인용, PlanViewDialog)
# 파일 위치: src/gui/plan_view_dialog.py
import tkinter as tk
from tkinter import ttk

from config import ASSIGNED_TYPE_LABELS


class PlanViewDialog(tk.Toplevel):
    """일차를 골라 그 날의 단어와 외움 여부를 보여준다. 읽기 전용이다."""

    def __init__(self, master, app):
        super().__init__(master)
        self.title("일차별 진도")
        self.transient(master)
        self.geometry("560x420")
        self.app = app

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Label(top, text="일차").pack(side="left")
        day_values = [str(day) for day in range(1, app.settings.current_day + 1)]
        self.day_box = ttk.Combobox(top, values=day_values, state="readonly", width=6)
        if day_values:
            self.day_box.set(day_values[-1])
        self.day_box.pack(side="left", padx=6)
        self.day_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.summary_label = ttk.Label(top, text="")
        self.summary_label.pack(side="right")

        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True, pady=8)
        self.table = ttk.Treeview(table_frame, columns=("word", "meaning", "type", "state"),
                                  show="headings", selectmode="browse")
        for column, title, width in (("word", "단어", 140), ("meaning", "뜻", 200),
                                     ("type", "구분", 70), ("state", "상태", 70)):
            self.table.heading(column, text=title)
            self.table.column(column, width=width)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.refresh()
        self.bind("<Escape>", lambda _event: self.destroy())

    def refresh(self) -> None:
        self.table.delete(*self.table.get_children())
        if not self.day_box.get():
            self.summary_label.configure(text="아직 만든 진도가 없습니다.")
            return
        day_no = int(self.day_box.get())
        meanings = {word.word: word.meaning_text for word in self.app.words}
        items = [item for item in self.app.plan_items if item.day == day_no]
        for item in items:
            self.table.insert("", "end", values=(
                item.word,
                meanings.get(item.word, "(단어장에 없음)"),
                ASSIGNED_TYPE_LABELS.get(item.assigned_type, item.assigned_type),
                "외움" if item.done else "남음",
            ))
        done_count = sum(1 for item in items if item.done)
        self.summary_label.configure(text=f"외움 {done_count} / 전체 {len(items)}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 단어장 탭: 목록 보기, 추가·삭제, CSV 불러오기·저장 (WordListTab)
# 파일 위치: src/gui/word_list_tab.py

from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from core.word_repository import WordRepository
from models import Word


class WordListTab(ttk.Frame):
    """단어장 화면. 단어 목록을 표로 보여주고 편집·파일 입출력을 맡는다."""

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="CSV 불러오기", command=self.on_load_csv).pack(side="left", padx=2)
        ttk.Button(toolbar, text="CSV 저장", command=self.on_save_csv).pack(side="left", padx=2)
        ttk.Button(toolbar, text="선택 삭제", command=self.on_delete).pack(side="left", padx=2)
        self.count_label = ttk.Label(toolbar, text="")
        self.count_label.pack(side="right")

        add_frame = ttk.Frame(self)
        add_frame.pack(fill="x", pady=8)
        ttk.Label(add_frame, text="단어").pack(side="left", padx=2)
        self.word_entry = ttk.Entry(add_frame, width=20)
        self.word_entry.pack(side="left", padx=2)
        ttk.Label(add_frame, text="뜻").pack(side="left", padx=(8, 2))
        self.meaning_entry = ttk.Entry(add_frame, width=30)
        self.meaning_entry.pack(side="left", padx=2)
        ttk.Button(add_frame, text="추가", command=self.on_add).pack(side="left", padx=2)
        ttk.Label(add_frame, text="뜻이 여러 개면 /로 구분").pack(side="left", padx=8)

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table_frame, columns=("word", "meaning"), show="headings", selectmode="extended")
        self.table.heading("word", text="단어")
        self.table.heading("meaning", text="뜻")
        self.table.column("word", width=200)
        self.table.column("meaning", width=400)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.refresh()

    def refresh(self) -> None:
        """app.words 내용을 표에 다시 그린다."""
        self.table.delete(*self.table.get_children())
        for word in self.app.words:
            self.table.insert("", "end", values=(word.word, word.meaning_text))
        self.count_label.configure(text=f"총 {len(self.app.words)}개")

    def on_add(self) -> None:
        word_text = self.word_entry.get().strip()
        meaning_text = self.meaning_entry.get().strip()
        if not word_text or not meaning_text:
            messagebox.showwarning("단어 추가", "단어와 뜻을 모두 입력하세요.")
            return
        if any(word.word == word_text for word in self.app.words):
            messagebox.showwarning("단어 추가", f"이미 있는 단어입니다: {word_text}")
            return

        meaning_list = [item.strip() for item in meaning_text.split("/") if item.strip()]
        self.app.words.append(Word(word=word_text, meaning_list=meaning_list))
        self._save_and_refresh()
        self.word_entry.delete(0, "end")
        self.meaning_entry.delete(0, "end")

    def on_delete(self) -> None:
        selected_items = self.table.selection()
        if not selected_items:
            return
        selected_words = {self.table.item(item, "values")[0] for item in selected_items}
        # 학습 기록은 남겨 둔다. 기록 처리는 설계서 T-01에서 정하기로 했다.
        self.app.words = [word for word in self.app.words if word.word not in selected_words]
        self._save_and_refresh()

    def on_load_csv(self) -> None:
        path = filedialog.askopenfilename(title="단어 CSV 불러오기", filetypes=[("CSV 파일", "*.csv")])
        if not path:
            return
        if not messagebox.askyesno("CSV 불러오기", "현재 단어장을 파일 내용으로 바꿉니다. 계속할까요?"):
            return
        try:
            words, skipped_count = WordRepository().load(path)
        except (ValueError, OSError) as error:
            messagebox.showerror("CSV 불러오기", str(error))
            return

        self.app.words = words
        self._save_and_refresh()
        if skipped_count:
            messagebox.showinfo("CSV 불러오기", f"중복되거나 빈 행 {skipped_count}개를 건너뛰었습니다.")

    def on_save_csv(self) -> None:
        path = filedialog.asksaveasfilename(title="단어 CSV 저장", defaultextension=".csv",
                                            filetypes=[("CSV 파일", "*.csv")])
        if not path:
            return
        WordRepository().save(self.app.words, path)
        messagebox.showinfo("CSV 저장", f"저장했습니다: {path}")

    def _save_and_refresh(self) -> None:
        """단어장 변경을 파일에 반영하고 화면을 갱신한다."""
        self.app.ensure_records_for_words()
        self.app.save_words()
        self.app.save_records()
        self.refresh()

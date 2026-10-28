#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 단어 수정 대화상자 (WordEditDialog)
# 파일 위치: src/gui/word_edit_dialog.py
from tkinter import messagebox, ttk
import tkinter as tk

from core.word_service import WordService
from models import Word


class WordEditDialog(tk.Toplevel):
    """단어와 뜻을 고치는 작은 창. 저장을 누르면 result에 새 값을 담고 닫힌다."""

    def __init__(self, master, target: Word, all_words):
        super().__init__(master)
        self.title("단어 수정")
        self.transient(master)
        self.resizable(False, False)
        self.target = target
        self.all_words = all_words
        self.result = None  # (새 단어, 뜻 목록)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="단어").grid(row=0, column=0, sticky="w", pady=4)
        self.word_entry = ttk.Entry(body, width=28)
        self.word_entry.insert(0, target.word)
        self.word_entry.grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(body, text="뜻").grid(row=1, column=0, sticky="w", pady=4)
        self.meaning_entry = ttk.Entry(body, width=40)
        self.meaning_entry.insert(0, target.meaning_text)
        self.meaning_entry.grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(body, text="뜻이 여러 개면 /로 구분").grid(row=2, column=1, sticky="w", padx=8)

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="취소", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="저장", command=self.on_save).pack(side="right", padx=4)

        self.bind("<Return>", lambda _event: self.on_save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.word_entry.focus_set()
        self.grab_set()
        self.wait_window(self)

    def on_save(self) -> None:
        word_text = self.word_entry.get().strip()
        meaning_text = self.meaning_entry.get().strip()
        error = WordService.validate(word_text, meaning_text, self.all_words, editing_word=self.target.word)
        if error:
            messagebox.showwarning("단어 수정", error, parent=self)
            return
        self.result = (word_text, WordService.split_meanings(meaning_text))
        self.destroy()

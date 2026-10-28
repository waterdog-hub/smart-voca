#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 단어장 탭: 검색·정렬, 추가·수정·삭제, CSV 불러오기·저장 (WordListTab)
# 파일 위치: src/gui/word_list_tab.py
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from core.word_repository import WordRepository
from core.word_service import WordService
from gui.word_edit_dialog import WordEditDialog
from models import Word


class WordListTab(ttk.Frame):
    """단어장 화면. 단어 목록을 표로 보여주고 검색·정렬·편집·파일 입출력을 맡는다."""

    COLUMN_TITLES = {"word": "단어", "meaning": "뜻"}

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.sort_column: Optional[str] = None
        self.sort_reverse = False

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="CSV 불러오기", command=self.on_load_csv).pack(side="left", padx=2)
        ttk.Button(toolbar, text="CSV 저장", command=self.on_save_csv).pack(side="left", padx=2)
        ttk.Button(toolbar, text="선택 수정", command=self.on_edit).pack(side="left", padx=2)
        ttk.Button(toolbar, text="선택 삭제", command=self.on_delete).pack(side="left", padx=2)
        self.count_label = ttk.Label(toolbar, text="")
        self.count_label.pack(side="right")

        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", pady=(8, 0))
        ttk.Label(search_frame, text="검색").pack(side="left", padx=2)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side="left", padx=2)
        self.search_var.trace_add("write", lambda *_args: self.refresh())
        ttk.Label(search_frame, text="단어나 뜻의 일부를 입력하세요. 열 제목을 누르면 정렬됩니다.").pack(side="left", padx=8)

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
        for column, title in self.COLUMN_TITLES.items():
            self.table.heading(column, text=title, command=lambda name=column: self.on_sort(name))
        self.table.column("word", width=200)
        self.table.column("meaning", width=400)
        self.table.bind("<Double-1>", lambda _event: self.on_edit())
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.refresh()

    def refresh(self) -> None:
        """app.words를 검색어와 정렬 기준에 맞춰 표에 다시 그린다."""
        visible_words = WordService.filter_by_keyword(self.app.words, self.search_var.get())
        if self.sort_column:
            visible_words = self._sorted(visible_words)

        self.table.delete(*self.table.get_children())
        for word in visible_words:
            self.table.insert("", "end", values=(word.word, word.meaning_text))

        total = len(self.app.words)
        if self.search_var.get().strip():
            self.count_label.configure(text=f"검색 결과 {len(visible_words)} / 총 {total}개")
        else:
            self.count_label.configure(text=f"총 {total}개")

    def on_sort(self, column: str) -> None:
        """같은 열을 또 누르면 내림차순으로 바꾼다."""
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self.refresh()

    def on_add(self) -> None:
        word_text = self.word_entry.get().strip()
        meaning_text = self.meaning_entry.get().strip()
        error = WordService.validate(word_text, meaning_text, self.app.words)
        if error:
            messagebox.showwarning("단어 추가", error)
            return
        self.app.words.append(Word(word=word_text, meaning_list=WordService.split_meanings(meaning_text)))
        self._save_and_refresh()
        self.word_entry.delete(0, "end")
        self.meaning_entry.delete(0, "end")

    def on_edit(self) -> None:
        selected_items = self.table.selection()
        if not selected_items:
            messagebox.showinfo("단어 수정", "고칠 단어를 선택하세요.")
            return
        word_text = self.table.item(selected_items[0], "values")[0]
        target = next((word for word in self.app.words if word.word == word_text), None)
        if target is None:
            return

        dialog = WordEditDialog(self, target, self.app.words)
        if dialog.result is None:
            return
        new_word, meaning_list = dialog.result
        self.app.update_word(target.word, new_word, meaning_list)
        self.refresh()

    def on_delete(self) -> None:
        selected_items = self.table.selection()
        if not selected_items:
            return
        selected_words = {self.table.item(item, "values")[0] for item in selected_items}
        message = (f"선택한 단어 {len(selected_words)}개를 삭제합니다.\n"
                   "모든 일차의 진도에서도 빠집니다. 학습 기록은 남습니다.\n계속할까요?")
        if not messagebox.askyesno("단어 삭제", message):
            return
        self.app.delete_words(selected_words)
        self.refresh()

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

        # 덮어쓰기 전에 기존 단어장을 백업한다 (설계 D-22)
        backup_path = self.app.backup_words_file()

        # 새 파일에 없는 단어는 진도에서도 빼야 한다 (삭제와 같은 규칙)
        old_words = {word.word for word in self.app.words}
        new_words = {word.word for word in words}
        self.app.words = words
        self.app.delete_words(old_words - new_words)
        self._save_and_refresh()

        messages = []
        if backup_path is not None:
            messages.append(f"이전 단어장을 백업했습니다: {backup_path.name}")
        if skipped_count:
            messages.append(f"중복되거나 빈 행 {skipped_count}개를 건너뛰었습니다.")
        if messages:
            messagebox.showinfo("CSV 불러오기", "\n".join(messages))

    def on_save_csv(self) -> None:
        path = filedialog.asksaveasfilename(title="단어 CSV 저장", defaultextension=".csv",
                                            filetypes=[("CSV 파일", "*.csv")])
        if not path:
            return
        WordRepository().save(self.app.words, path)
        messagebox.showinfo("CSV 저장", f"저장했습니다: {path}")

    def _sorted(self, words):
        """정렬 기준 열의 글자 순서로 정렬한다. 대소문자는 구분하지 않는다."""
        if self.sort_column == "meaning":
            key = lambda word: word.meaning_text.lower()
        else:
            key = lambda word: word.word.lower()
        return sorted(words, key=key, reverse=self.sort_reverse)

    def _save_and_refresh(self) -> None:
        """단어장 변경을 파일에 반영하고 화면을 갱신한다."""
        self.app.ensure_records_for_words()
        self.app.save_words()
        self.app.save_records()
        self.refresh()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 암기 탭: 일차 진도를 카드로 외우고 암기 기록 (MemorizeTab)
# 파일 위치: src/gui/memorize_tab.py

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from typing import Dict, List

from models import DayPlanItem


class MemorizeTab(ttk.Frame):
    """오늘 일차 진도를 카드 한 장씩 보여준다. '외움'은 완료, '다시'는 뒤로 보낸다."""

    def __init__(self, master, app):
        super().__init__(master, padding=12)
        self.app = app
        self.queue: List[DayPlanItem] = []   # 아직 외우지 않은 항목 (앞에서부터 보여줌)
        self.meaning_visible = False

        top = ttk.Frame(self)
        top.pack(fill="x")
        self.info_label = ttk.Label(top, text="")
        self.info_label.pack(side="left")
        self.next_day_button = ttk.Button(top, text="다음 일차 만들기", command=self.on_create_next_day)
        self.next_day_button.pack(side="right")

        card = ttk.Frame(self, padding=24, relief="groove")
        card.pack(fill="both", expand=True, pady=16)
        self.word_label = ttk.Label(card, text="", font=("맑은 고딕", 28, "bold"))
        self.word_label.pack(pady=(20, 10))
        self.meaning_label = ttk.Label(card, text="", font=("맑은 고딕", 20))
        self.meaning_label.pack(pady=10)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        self.show_button = ttk.Button(buttons, text="뜻 보기", command=self.on_show_meaning)
        self.show_button.pack(side="left", padx=4)
        self.again_button = ttk.Button(buttons, text="다시", command=self.on_again)
        self.again_button.pack(side="right", padx=4)
        self.remember_button = ttk.Button(buttons, text="외움", command=self.on_remember)
        self.remember_button.pack(side="right", padx=4)

        self.refresh()

    def refresh(self) -> None:
        """현재 일차 진도 상태를 읽어 화면을 다시 그린다."""
        items = self.app.current_day_items()
        day_no = self.app.settings.current_day
        not_done = [item for item in items if not item.done]

        if day_no == 0:
            self.info_label.configure(text="아직 진도가 없습니다. '다음 일차 만들기'를 누르세요.")
        else:
            self.info_label.configure(text=f"{day_no}일차 · 남은 단어 {len(not_done)} / 전체 {len(items)}")

        can_create_next = day_no == 0 or self.app.is_current_day_complete()
        self.next_day_button.configure(state="normal" if can_create_next else "disabled")

        self.queue = not_done
        self.meaning_visible = False
        self._show_current()

    def on_show_meaning(self) -> None:
        self.meaning_visible = True
        self._show_current()

    def on_remember(self) -> None:
        if not self.queue:
            return
        item = self.queue.pop(0)
        item.done = True

        record = self.app.records[item.word]
        record.memorized_count += 1
        if record.first_memorized_day == 0:
            record.first_memorized_day = self.app.settings.current_day
        record.last_memorized_date = date.today().isoformat()

        self.app.save_plan()
        self.app.save_records()
        self.refresh()

    def on_again(self) -> None:
        # 카드를 같은 일차 안의 맨 뒤로 보내고 저장한다. 다음 실행 때도 같은 순서로 나온다 (설계 D-10)
        if not self.queue:
            return
        card = self.queue.pop(0)
        self.app.plan_items.remove(card)
        day_positions = [index for index, item in enumerate(self.app.plan_items)
                         if item.day == self.app.settings.current_day]
        self.app.plan_items.insert(day_positions[-1] + 1, card)
        self.app.save_plan()

        self.queue.append(card)
        self.meaning_visible = False
        self._show_current()

    def on_create_next_day(self) -> None:
        if self.app.create_next_day_plan():
            messagebox.showinfo("진도 생성", f"{self.app.settings.current_day}일차 진도를 만들었습니다.")
            self.refresh()
        else:
            messagebox.showwarning("진도 생성", "진도를 만들 단어가 없습니다. 단어장을 확인하세요.")

    def _show_current(self) -> None:
        """큐 맨 앞 카드를 화면에 보여준다. 큐가 비면 완료 메시지를 보여준다."""
        has_card = bool(self.queue)
        button_state = "normal" if has_card else "disabled"
        for button in (self.show_button, self.remember_button, self.again_button):
            button.configure(state=button_state)

        if not has_card:
            # 진도가 없으면 카드를 비우고, 상단 안내 문구에 맡긴다
            day_items = self.app.current_day_items()
            if day_items and all(item.done for item in day_items):
                self.word_label.configure(text="오늘 진도를 모두 외웠습니다.")
            else:
                self.word_label.configure(text="")
            self.meaning_label.configure(text="")
            return

        word_text = self.queue[0].word
        self.word_label.configure(text=word_text)
        if self.meaning_visible:
            self.meaning_label.configure(text=self._meaning_of(word_text))
        else:
            self.meaning_label.configure(text="")

    def _meaning_of(self, word_text: str) -> str:
        meanings: Dict[str, str] = {word.word: word.meaning_text for word in self.app.words}
        return meanings.get(word_text, "")

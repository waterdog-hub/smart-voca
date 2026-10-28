#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 암기 탭: 일차 진도를 카드로 외우고 암기 기록, 진행률·단축키 (MemorizeTab)
# 파일 위치: src/gui/memorize_tab.py
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from typing import Dict, List

from gui.plan_view_dialog import PlanViewDialog
from models import DayPlanItem


class MemorizeTab(ttk.Frame):
    """오늘 일차 진도를 카드 한 장씩 보여준다. '외움'은 완료, '다시'는 뒤로 보낸다.
    단축키: ↑ 뜻 보기 · → 외움 · ← 다시
    """

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
        ttk.Button(top, text="일차별 진도", command=self.on_open_plan_view).pack(side="right", padx=6)

        self.progress = ttk.Progressbar(self, maximum=1, value=0)
        self.progress.pack(fill="x", pady=(8, 0))

        card = ttk.Frame(self, padding=24, relief="groove")
        card.pack(fill="both", expand=True, pady=16)
        self.word_label = ttk.Label(card, text="", font=("맑은 고딕", 28, "bold"))
        self.word_label.pack(pady=(20, 10))
        self.meaning_label = ttk.Label(card, text="", font=("맑은 고딕", 20))
        self.meaning_label.pack(pady=10)
        self.hint_label = ttk.Label(card, text="", font=("맑은 고딕", 10))
        self.hint_label.pack(pady=(10, 0))

        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        self.show_button = ttk.Button(buttons, text="뜻 보기 (↑)", command=self.on_show_meaning)
        self.show_button.pack(side="left", padx=4)
        self.again_button = ttk.Button(buttons, text="다시 (←)", command=self.on_again)
        self.again_button.pack(side="right", padx=4)
        self.remember_button = ttk.Button(buttons, text="외움 (→)", command=self.on_remember)
        self.remember_button.pack(side="right", padx=4)

        self.refresh()

    def refresh(self) -> None:
        """현재 일차 진도 상태를 읽어 화면을 다시 그린다."""
        items = self.app.current_day_items()
        day_no = self.app.settings.current_day
        not_done = [item for item in items if not item.done]

        self.progress.configure(maximum=max(len(items), 1), value=len(items) - len(not_done))
        if not self.app.words:
            info_text = "단어장에 단어가 없습니다. 단어장 탭에서 단어를 추가하세요."
        elif day_no == 0:
            info_text = "아직 진도가 없습니다. '다음 일차 만들기'를 누르세요."
        else:
            info_text = f"{day_no}일차 · 남은 단어 {len(not_done)} / 전체 {len(items)}"
        self.info_label.configure(text=info_text)

        can_create_next = bool(self.app.words) and (day_no == 0 or self.app.is_current_day_complete())
        self.next_day_button.configure(state="normal" if can_create_next else "disabled")

        self.queue = not_done
        self.meaning_visible = False
        self._show_current()

    def handle_key(self, keysym: str) -> None:
        """메인 창이 넘겨주는 키 입력을 처리한다."""
        if keysym == "Up":
            self.on_show_meaning()
        elif keysym == "Right":
            self.on_remember()
        elif keysym == "Left":
            self.on_again()

    def on_show_meaning(self) -> None:
        if not self.queue:
            return
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
            return
        if not self.app.words:
            reason = "단어장에 단어가 없습니다."
        else:
            reason = ("모든 단어를 외웠고, 오답 기준을 넘긴 단어와 복습할 단어가 없어 진도를 만들 수 없습니다.\n"
                      "시험으로 오답을 쌓거나 설정의 오답 기준을 확인하세요.")
        messagebox.showwarning("진도 생성", reason)

    def on_open_plan_view(self) -> None:
        PlanViewDialog(self, self.app)

    def _show_current(self) -> None:
        """큐 맨 앞 카드를 화면에 보여준다. 큐가 비면 상황에 맞는 안내를 보여준다."""
        has_card = bool(self.queue)
        button_state = "normal" if has_card else "disabled"
        for button in (self.show_button, self.remember_button, self.again_button):
            button.configure(state=button_state)

        if not has_card:
            self.word_label.configure(text=self._empty_message())
            self.meaning_label.configure(text="")
            self.hint_label.configure(text="")
            return

        word_text = self.queue[0].word
        self.word_label.configure(text=word_text)
        if self.meaning_visible:
            self.meaning_label.configure(text=self._meaning_of(word_text))
        else:
            self.meaning_label.configure(text="")
        self.hint_label.configure(text="" if self.meaning_visible else "뜻 보기(↑)를 누르면 뜻이 보입니다.")

    def _empty_message(self) -> str:
        """카드가 없을 때 보여줄 문구. 진도가 끝났는지, 비었는지를 구분한다."""
        if not self.app.words:
            return ""
        items = self.app.current_day_items()
        if not items:
            return "이 일차에 남은 단어가 없습니다. '다음 일차 만들기'를 누르세요."
        if all(item.done for item in items):
            return "오늘 진도를 모두 외웠습니다."
        return ""

    def _meaning_of(self, word_text: str) -> str:
        meanings: Dict[str, str] = {word.word: word.meaning_text for word in self.app.words}
        return meanings.get(word_text, "")

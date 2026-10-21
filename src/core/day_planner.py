#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 일차별 암기 진도 생성 (신규·복습·오답 배정) (DayPlanner)
# 파일 위치: src/core/day_planner.py

import random
from typing import Dict, Iterable, List, Optional

from models import DayPlanItem, Settings, StudyRecord, Word


class DayPlanner:
    """설정과 학습 기록을 보고 다음 일차의 진도를 만든다.

    저장은 하지 않는다. 만든 결과를 PlanRepository로 저장하는 일은 호출자가 한다.
    """

    def __init__(self, rng: Optional[random.Random] = None):
        # 테스트에서는 시드를 고정한 Random을 넣어 결과를 재현한다 (설계 D-03)
        self._rng = rng or random.Random()

    def create_next_day_plan(
        self,
        words: List[Word],
        records: Dict[str, StudyRecord],
        previous_day_items: List[DayPlanItem],
        settings: Settings,
    ) -> List[DayPlanItem]:
        """다음 일차(current_day + 1)의 진도 항목 목록을 만든다."""
        if not words:
            return []

        day_no = settings.current_day + 1

        if self.is_all_memorized(words, records):
            # 모두 외운 뒤: 오답 중심으로 진행하고, 부족한 칸은 복습으로 채운다 (기획서 §3.6)
            wrong_words = self.pick_wrong_words(
                words, records, settings.wrong_threshold, settings.daily_wrong_count, exclude=set())
            review_slots = settings.daily_review_count + (settings.daily_wrong_count - len(wrong_words))
            review_words = self.pick_review_words(previous_day_items, review_slots, exclude=set(wrong_words))
            new_words: List[str] = []
        else:
            new_words = self.pick_new_words(words, records, settings.daily_new_count)
            review_words = self.pick_review_words(
                previous_day_items, settings.daily_review_count, exclude=set(new_words))
            used_words = set(new_words) | set(review_words)
            wrong_words = self.pick_wrong_words(
                words, records, settings.wrong_threshold, settings.daily_wrong_count, exclude=used_words)

        plan_items: List[DayPlanItem] = []
        plan_items += [DayPlanItem(day_no, word, "new") for word in new_words]
        plan_items += [DayPlanItem(day_no, word, "review") for word in review_words]
        plan_items += [DayPlanItem(day_no, word, "wrong") for word in wrong_words]
        return plan_items

    def is_all_memorized(self, words: List[Word], records: Dict[str, StudyRecord]) -> bool:
        """모든 단어를 한 번 이상 외웠으면 True다."""
        return all(self._memorized_count(word.word, records) >= 1 for word in words)

    def pick_new_words(self, words: List[Word], records: Dict[str, StudyRecord], count: int) -> List[str]:
        """아직 외우지 않은 단어를 단어장 순서대로 count개 고른다 (설계 D-02)."""
        candidates = [
            word.word for word in words
            if self._memorized_count(word.word, records) == 0
        ]
        return candidates[:count]

    def pick_review_words(
        self,
        previous_day_items: List[DayPlanItem],
        count: int,
        exclude: Iterable[str],
    ) -> List[str]:
        """전날 외운(done) 단어 중 exclude에 없는 단어를 무작위로 count개 고른다 (설계 D-03)."""
        excluded = set(exclude)
        pool = [
            item.word for item in previous_day_items
            if item.done and item.word not in excluded
        ]
        pool = list(dict.fromkeys(pool))  # 중복 제거, 순서 유지
        if count <= 0 or not pool:
            return []
        return self._rng.sample(pool, min(count, len(pool)))

    def pick_wrong_words(
        self,
        words: List[Word],
        records: Dict[str, StudyRecord],
        threshold: int,
        count: int,
        exclude: Iterable[str],
    ) -> List[str]:
        """오답 횟수가 threshold 이상인 단어를 오답 많은 순으로 count개 고른다.

        동점이면 단어장 순서를 따른다 (설계 D-04).
        """
        excluded = set(exclude)
        order_index = {word.word: index for index, word in enumerate(words)}
        candidates = []
        for word in words:
            if word.word in excluded:
                continue
            record = records.get(word.word)
            wrong_count = record.wrong_count if record else 0
            if wrong_count >= threshold:
                candidates.append((wrong_count, word.word))
        candidates.sort(key=lambda pair: (-pair[0], order_index[pair[1]]))
        return [word_text for _, word_text in candidates[:count]]

    def _memorized_count(self, word_text: str, records: Dict[str, StudyRecord]) -> int:
        """기록이 없는 단어는 외운 횟수 0으로 본다."""
        record = records.get(word_text)
        return record.memorized_count if record else 0

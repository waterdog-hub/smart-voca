#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 다음 일차 생성 (core.day_planner 호출), 암기 처리, 진행률 (API 설계 §5)
# 파일 위치: src/web/services/plan_service.py

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.day_planner import DayPlanner
from models import DayPlanItem, Settings, StudyRecord, Word as CoreWord
from web.db.tables import PlanItem, Word
from web.errors import ApiError
from web.repositories import plan_repository, setting_repository, word_repository

# zoneinfo는 Windows에서 tzdata 패키지가 더 필요하다. 한국은 서머타임이 없어 고정값으로 충분하다
KOREA_TIME = timezone(timedelta(hours=9))

NO_WORDS = "NO_WORDS"
WRONG_THRESHOLD_NOT_MET = "WRONG_THRESHOLD_NOT_MET"
CURRENT_DAY_INCOMPLETE = "CURRENT_DAY_INCOMPLETE"
PLAN_NOT_READY_MESSAGES = {
    NO_WORDS: "단어장에 단어가 없습니다. 먼저 단어를 추가하세요.",
    WRONG_THRESHOLD_NOT_MET: (
        "모든 단어를 외웠고, 오답 기준을 넘긴 단어와 복습할 단어가 없어 진도를 만들 수 없습니다. "
        "시험으로 오답을 쌓거나 설정의 오답 기준을 확인하세요."
    ),
    CURRENT_DAY_INCOMPLETE: "현재 일차를 먼저 끝내세요.",
}


def today_in_korea() -> date:
    return datetime.now(KOREA_TIME).date()


def _plan_not_ready(reason: str) -> ApiError:
    return ApiError(409, "PLAN_NOT_READY", PLAN_NOT_READY_MESSAGES[reason], reason=reason)


@dataclass(frozen=True)
class Progress:
    total_words: int
    memorized_words: int
    current_day: int
    day_total: int
    day_done: int

    @property
    def day_complete(self) -> bool:
        # 단어 삭제로 현재 일차가 비어도 다음 일차를 만들 수 있어야 한다 (D-18)
        return self.day_done == self.day_total


class PlanService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def current_day(self) -> int:
        return setting_repository.get_settings(self.db, self.user_id).current_day

    def list_days(self) -> list[tuple[int, int, int]]:
        return plan_repository.list_day_summaries(self.db, self.user_id)

    def get_day_items(self, day: int) -> list[tuple[PlanItem, Word]]:
        items = plan_repository.list_day_items(self.db, self.user_id, day)
        if not items:
            raise ApiError(404, "NOT_FOUND", "찾을 수 없습니다.")
        return items

    def progress(self) -> Progress:
        current_day = self.current_day()
        items = plan_repository.list_day_items(self.db, self.user_id, current_day)
        return Progress(
            total_words=plan_repository.count_active_words(self.db, self.user_id),
            memorized_words=plan_repository.count_memorized_words(self.db, self.user_id),
            current_day=current_day,
            day_total=len(items),
            day_done=sum(1 for item, _ in items if item.done),
        )

    def create_next_day(self) -> int:
        """다음 일차를 만들고 그 번호를 돌려준다."""
        setting = setting_repository.get_settings(self.db, self.user_id)
        current_day = setting.current_day
        current_items = plan_repository.list_day_items(self.db, self.user_id, current_day)
        if any(not item.done for item, _ in current_items):
            raise _plan_not_ready(CURRENT_DAY_INCOMPLETE)

        words = word_repository.list_all_active_words(self.db, self.user_id)
        if not words:
            raise _plan_not_ready(NO_WORDS)
        word_ids = {word.word: word.id for word in words}

        planned = DayPlanner().create_next_day_plan(
            # core는 단어 문자열을 키로 쓴다. 한 회원의 단어는 유일하므로 안전하다 (구현 계획 §2.3)
            [CoreWord(word.word) for word in words],
            {
                word: StudyRecord(word, memorized_count=memorized, wrong_count=wrong)
                for word, memorized, wrong in plan_repository.load_records(self.db, self.user_id)
            },
            [
                DayPlanItem(current_day, word.word, item.assigned_type, item.done)
                for item, word in current_items
            ],
            Settings(
                daily_new_count=setting.daily_new_count,
                daily_review_count=setting.daily_review_count,
                daily_wrong_count=setting.daily_wrong_count,
                wrong_threshold=setting.wrong_threshold,
                current_day=current_day,
            ),
        )
        if not planned:
            raise _plan_not_ready(WRONG_THRESHOLD_NOT_MET)

        # 먼저 일차를 올린다. 동시 요청에서 진 쪽은 여기서 멈추고 항목을 넣지 않는다
        new_day = current_day + 1
        lost_race = not plan_repository.raise_current_day(self.db, self.user_id, current_day)
        if not lost_race:
            self.db.add_all(
                PlanItem(
                    user_id=self.user_id,
                    day=new_day,
                    word_id=word_ids[planned_item.word],
                    assigned_type=planned_item.assigned_type,
                    position=position,
                )
                for position, planned_item in enumerate(planned, start=1)
            )
            try:
                self.db.commit()
            except IntegrityError:
                lost_race = True
        if lost_race:
            self.db.rollback()
            raise _plan_not_ready(CURRENT_DAY_INCOMPLETE)
        self.db.expire(setting)
        return new_day

    def _find_current_item(self, item_id: int) -> tuple[PlanItem, Word, int]:
        found = plan_repository.find_item(self.db, self.user_id, item_id)
        if found is None:
            raise ApiError(404, "NOT_FOUND", "찾을 수 없습니다.")
        item, word = found
        current_day = self.current_day()
        if item.day != current_day:
            # 지난 일차 복습은 화면에서만 진행한다. 기록과 진도를 바꾸지 않는다 (D-16)
            raise ApiError(
                409, "PLAN_ITEM_NOT_CURRENT", "지난 일차의 기록은 바꿀 수 없습니다."
            )
        return item, word, current_day

    def mark_memorized(self, item_id: int) -> tuple[PlanItem, Word]:
        item, word, current_day = self._find_current_item(item_id)
        # 두 번 보내도 한 번만 집계한다. 완료로 실제 바꾼 요청만 기록을 올린다 (D-API05)
        if plan_repository.mark_done(self.db, self.user_id, item_id):
            plan_repository.add_memorized(
                self.db, self.user_id, item.word_id, current_day, today_in_korea()
            )
        self.db.commit()
        self.db.refresh(item)
        return item, word

    def move_to_end(self, item_id: int) -> tuple[PlanItem, Word]:
        item, word, current_day = self._find_current_item(item_id)
        if not item.done:
            item.position = plan_repository.next_position(self.db, self.user_id, current_day)
            self.db.commit()
        return item, word

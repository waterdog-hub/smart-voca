#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원 설정의 값 규칙 검사와 저장 (API 설계 §4, D-23)
# 파일 위치: src/web/services/setting_service.py

from dataclasses import dataclass

from sqlalchemy.orm import Session

from config import TEST_DIRECTION_LABELS, TEST_FORMAT_LABELS
from web.db.tables import TEST_DIRECTIONS, TEST_FORMATS, UserSetting
from web.errors import ApiError
from web.repositories import setting_repository
from web.schemas.settings import SettingsData

MAX_COUNT_VALUE = 9999


@dataclass(frozen=True)
class CountField:
    name: str
    label: str
    minimum: int
    maximum: int = MAX_COUNT_VALUE


# 화면도 이 목록으로 칸을 그린다. 규칙을 한 곳에 두어 서버와 화면이 어긋나지 않게 한다.
# 최소값은 데스크톱 앱과 같다. 복습·오답 0은 신규 단어만 외우는 정상 사용이다
COUNT_FIELDS = (
    CountField("daily_new_count", "하루 신규 단어 수", 1),
    CountField("daily_review_count", "하루 복습 단어 수", 0),
    CountField("daily_wrong_count", "하루 오답 단어 최대 수", 0),
    CountField("wrong_threshold", "오답 단어 기준 (이 횟수 이상)", 1),
)
# 표시 문구는 데스크톱 앱과 같은 대응표를 쓴다. 허용 값의 기준은 DB 제약과 같은 tables.py다
FORMAT_CHOICES = tuple((code, label) for label, code in TEST_FORMAT_LABELS.items())
DIRECTION_CHOICES = tuple((code, label) for label, code in TEST_DIRECTION_LABELS.items())
CHOICE_ERROR = "목록에서 골라 주세요."


def find_setting_problems(values: SettingsData) -> dict[str, str]:
    problems = {}
    for field in COUNT_FIELDS:
        number = getattr(values, field.name)
        if not field.minimum <= number <= field.maximum:
            problems[field.name] = f"{field.minimum} 이상 {field.maximum} 이하로 입력해 주세요."
    if values.test_format not in TEST_FORMATS:
        problems["test_format"] = CHOICE_ERROR
    if values.test_direction not in TEST_DIRECTIONS:
        problems["test_direction"] = CHOICE_ERROR
    return problems


class SettingService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def get(self) -> UserSetting:
        return setting_repository.get_settings(self.db, self.user_id)

    def save(self, values: SettingsData) -> UserSetting:
        problems = find_setting_problems(values)
        if problems:
            raise ApiError(400, "VALIDATION_FAILED", "입력값을 확인해 주세요.", fields=problems)
        row = self.get()
        # 받은 칸만 바꾼다. ORM은 바뀐 열만 저장하므로 진도 생성이 올린 current_day를 덮어쓰지 않는다
        for name, value in values.model_dump().items():
            setattr(row, name, value)
        self.db.commit()
        return row

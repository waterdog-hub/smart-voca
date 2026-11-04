#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 설정 API의 요청과 응답 형식 (API 설계 §4)
# 파일 위치: src/web/schemas/settings.py

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

# 값의 범위와 한글 안내는 서비스에서 처리한다. 여기서는 형식과 과도한 길이만 막는다
MAX_CHOICE_LENGTH = 20

ChoiceText = Annotated[str, Field(max_length=MAX_CHOICE_LENGTH)]


class SettingsData(BaseModel):
    # 현재 일차와 카드 위치를 함께 보내면 무시하지 않고 거절한다 (FR-SET-03, D-W10).
    # 응답에도 두 값을 넣지 않아, 받은 값을 그대로 저장하는 화면이 거절당하지 않는다
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    # StrictInt는 "5"와 true를 숫자로 바꾸지 않는다. true가 1로 저장되는 일을 막는다
    daily_new_count: StrictInt
    daily_review_count: StrictInt
    daily_wrong_count: StrictInt
    wrong_threshold: StrictInt
    test_format: ChoiceText
    test_direction: ChoiceText

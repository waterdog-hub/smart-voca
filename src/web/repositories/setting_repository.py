#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원별 설정의 DB 읽기. 설정 행은 가입할 때 함께 만든다
# 파일 위치: src/web/repositories/setting_repository.py

from sqlalchemy.orm import Session

from web.db.tables import UserSetting


def get_settings(db: Session, user_id: int) -> UserSetting:
    row = db.get(UserSetting, user_id)
    if row is None:
        # 회원에게는 항상 설정 행이 있어야 한다. 없으면 데이터 오류이므로 숨기지 않는다
        raise LookupError(f"settings row is missing for user {user_id}")
    return row

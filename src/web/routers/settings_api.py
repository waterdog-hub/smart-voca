#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원 설정 조회와 저장 API (API 설계 §4)
# 파일 위치: src/web/routers/settings_api.py

from fastapi import APIRouter

from web.dependencies import DbSession, LoggedIn, VerifiedWrite
from web.schemas.settings import SettingsData
from web.services.setting_service import SettingService

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("")
def get_settings(current: LoggedIn, db: DbSession) -> SettingsData:
    return SettingsData.model_validate(SettingService(db, current.user.id).get())


@router.put("")
def save_settings(payload: SettingsData, current: VerifiedWrite, db: DbSession) -> SettingsData:
    return SettingsData.model_validate(SettingService(db, current.user.id).save(payload))

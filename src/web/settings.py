#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 환경변수와 .env에서 웹 서비스 설정을 읽는다
# 파일 위치: src/web/settings.py

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env에는 아직 쓰지 않는 항목도 있을 수 있으므로 모르는 항목은 무시한다
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 설정을 빠뜨린 운영 서버에서 API 문서가 열리지 않도록 기본값을 production으로 둔다 (D-API07)
    app_env: Literal["local", "production"] = "production"
    # 기본값을 두지 않는다. 운영에서 빠뜨렸을 때 빈 SQLite로 조용히 뜨는 사고를 막는다
    database_url: str = Field(min_length=1)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

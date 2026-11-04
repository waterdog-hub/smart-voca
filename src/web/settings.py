#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 환경변수와 .env에서 웹 서비스 설정을 읽는다
# 파일 위치: src/web/settings.py

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 개발 전용 값이다. 운영에서는 아래 검사가 이 기본값을 쓰지 못하게 막는다
LOCAL_AUTH_HASH_KEY = "local-development-only-auth-hash-key"
LOCAL_PUBLIC_BASE_URL = "http://127.0.0.1:8000"


class Settings(BaseSettings):
    # .env에는 아직 쓰지 않는 항목도 있을 수 있으므로 모르는 항목은 무시한다
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 설정을 빠뜨린 운영 서버에서 API 문서가 열리지 않도록 기본값을 production으로 둔다 (D-API07)
    # demo는 ngrok으로 여는 시연용이다 (D-W19). 인터넷에 열리므로 보안 기준은 운영과 같다
    app_env: Literal["local", "demo", "production"] = "production"
    # 기본값을 두지 않는다. 운영에서 빠뜨렸을 때 빈 SQLite로 조용히 뜨는 사고를 막는다
    database_url: str = Field(min_length=1)
    # 이메일과 IP는 경우의 수가 작아 키 없는 해시는 쉽게 되돌릴 수 있다 (이슈 #9)
    auth_hash_key: str | None = Field(default=None, min_length=32)
    # 메일 링크 주소. 요청의 Host 헤더는 조작할 수 있어 쓰지 않는다 (이슈 #9)
    public_base_url: str | None = None
    session_ttl_absolute_days: int = Field(default=14, gt=0)
    session_ttl_idle_days: int = Field(default=3, gt=0)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_public(self) -> bool:
        """인터넷에 열리는 환경이다. API 문서를 닫고 쿠키에 Secure를 붙이고 비밀값을 요구한다."""
        return self.app_env != "local"

    @property
    def auto_verifies_email(self) -> bool:
        # 별도 설정 항목을 두지 않는다. 운영에서 실수로 켤 수 있는 길을 만들지 않기 위해서다 (이슈 #11)
        return self.app_env == "demo"

    @model_validator(mode="after")
    def fill_or_require_auth_values(self) -> "Settings":
        if self.is_public:
            if self.auth_hash_key is None:
                raise ValueError("운영과 시연 환경에는 AUTH_HASH_KEY가 필요합니다.")
            if self.public_base_url is None or not self.public_base_url.startswith("https://"):
                raise ValueError("운영과 시연 환경의 PUBLIC_BASE_URL은 https 주소여야 합니다.")
        else:
            self.auth_hash_key = self.auth_hash_key or LOCAL_AUTH_HASH_KEY
            self.public_base_url = self.public_base_url or LOCAL_PUBLIC_BASE_URL
        self.public_base_url = self.public_base_url.rstrip("/")
        return self

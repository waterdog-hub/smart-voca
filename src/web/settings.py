#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 환경변수와 .env에서 웹 서비스 설정을 읽는다
# 파일 위치: src/web/settings.py

import secrets
from pathlib import Path
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
    # school은 학교 서버(기말 과제 배포)용이다. 메일과 인터넷이 없어 가입 즉시 인증하고 http에서도 쿠키가 동작하게 한다
    app_env: Literal["local", "demo", "school", "production"] = "production"
    # 기본값을 두지 않는다. 운영에서 빠뜨렸을 때 빈 SQLite로 조용히 뜨는 사고를 막는다
    # 학교 서버는 DATABASE_URL 대신 DB_PATH(/data/voca.db)를 준다. 그때는 아래 검사에서 SQLite 주소로 바꾼다
    database_url: str | None = Field(default=None, min_length=1)
    db_path: str | None = Field(default=None, min_length=1)
    # 학교 서버가 주는 비밀값. AUTH_HASH_KEY가 없으면 이 값을 쓴다 (Dockerfile 구성 R-08)
    secret_key: str | None = Field(default=None, min_length=1)
    # 이메일과 IP는 경우의 수가 작아 키 없는 해시는 쉽게 되돌릴 수 있다 (이슈 #9)
    auth_hash_key: str | None = Field(default=None, min_length=32)
    # 메일 링크 주소. 요청의 Host 헤더는 조작할 수 있어 쓰지 않는다 (이슈 #9)
    public_base_url: str | None = None
    session_ttl_absolute_days: int = Field(default=14, gt=0)
    session_ttl_idle_days: int = Field(default=3, gt=0)
    # 소셜 로그인 (M8). 키가 있는 제공자만 켠다. 시연 환경에서는 켜지 않는다 (이슈 #19)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    kakao_rest_api_key: str | None = None
    kakao_client_secret: str | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_public(self) -> bool:
        """인터넷에 열리는 환경이다. API 문서를 닫고 쿠키에 Secure를 붙이고 비밀값을 요구한다."""
        return self.app_env != "local"

    @property
    def is_school(self) -> bool:
        return self.app_env == "school"

    @property
    def uses_secure_cookie(self) -> bool:
        # 학교 서버는 http로 접속할 수도 있어 Secure를 붙이면 로그인 쿠키가 전송되지 않는다
        return self.is_public and not self.is_school

    @property
    def auto_verifies_email(self) -> bool:
        # 별도 설정 항목을 두지 않는다. 운영에서 실수로 켤 수 있는 길을 만들지 않기 위해서다 (이슈 #11)
        # 학교 서버는 메일을 보낼 수 없으므로 시연 환경처럼 가입 즉시 인증한다
        return self.app_env in ("demo", "school")

    @model_validator(mode="after")
    def fill_or_require_auth_values(self) -> "Settings":
        self.database_url = self.database_url or _sqlite_url(self.db_path)
        if self.database_url is None:
            raise ValueError("DATABASE_URL 또는 DB_PATH가 필요합니다.")
        if self.is_school:
            # 학교 서버는 공개 주소를 알려 주지 않는다. 메일을 보내지 않으므로 링크 주소는 쓰이지 않는다
            self.auth_hash_key = self.auth_hash_key or _school_hash_key(self.secret_key, self.db_path)
            self.public_base_url = (self.public_base_url or "/").rstrip("/")
            return self
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


def _sqlite_url(db_path: str | None) -> str | None:
    # /data/voca.db 같은 절대 경로는 sqlite:////data/voca.db가 된다
    return f"sqlite:///{db_path}" if db_path else None


SECRET_FILE_NAME = ".secret_key"
MIN_HASH_KEY_LENGTH = 32


def _school_hash_key(secret_key: str | None, db_path: str | None) -> str:
    """학교 서버의 해시 키. SECRET_KEY가 있으면 쓰고, 없으면 무작위로 만든다 (R-08)."""
    if secret_key:
        # SECRET_KEY가 짧아도 키 길이 조건(32자)을 채우도록 늘린다. 같은 SECRET_KEY면 같은 키가 된다
        return (secret_key * (MIN_HASH_KEY_LENGTH // len(secret_key) + 1))[: max(MIN_HASH_KEY_LENGTH, len(secret_key))]
    # 이메일 해시가 재시작마다 바뀌면 로그인할 수 없으므로, 만든 키를 DB 옆(/data)에 저장해 다시 쓴다
    if db_path:
        key_file = Path(db_path).parent / SECRET_FILE_NAME
        try:
            saved = key_file.read_text(encoding="utf-8").strip()
            if len(saved) >= MIN_HASH_KEY_LENGTH:
                return saved
        except OSError:
            pass
        new_key = secrets.token_urlsafe(48)
        try:
            key_file.write_text(new_key, encoding="utf-8")
        except OSError:
            # 저장할 수 없어도 시작은 한다. 재시작하면 다시 로그인해야 한다
            pass
        return new_key
    return secrets.token_urlsafe(48)

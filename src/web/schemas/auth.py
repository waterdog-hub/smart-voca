#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 인증 API의 요청과 응답 형식
# 파일 위치: src/web/schemas/auth.py

from pydantic import BaseModel, Field

from web.db.tables import User
from web.security.passwords import MAX_PASSWORD_LENGTH

# 칸별 규칙과 한글 안내는 서비스에서 처리한다. 여기서는 형식과 과도한 길이만 막는다
MAX_REQUEST_EMAIL_LENGTH = 320
MAX_REQUEST_NAME_LENGTH = 1000
MAX_REQUEST_PASSWORD_LENGTH = 1000
MAX_MAIL_TOKEN_LENGTH = 200


class SignupRequest(BaseModel):
    email: str = Field(max_length=MAX_REQUEST_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_REQUEST_PASSWORD_LENGTH)
    display_name: str = Field(max_length=MAX_REQUEST_NAME_LENGTH)
    terms_agreed: bool
    privacy_agreed: bool


class LoginRequest(BaseModel):
    email: str = Field(max_length=MAX_REQUEST_EMAIL_LENGTH)
    # 긴 입력으로 해시 계산 부담을 주지 못하게 가입 규칙과 같은 길이까지만 받는다
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=MAX_MAIL_TOKEN_LENGTH)


class UserSummary(BaseModel):
    email: str
    display_name: str
    email_verified: bool

    @classmethod
    def from_user(cls, user: User) -> "UserSummary":
        return cls(
            email=user.email,
            display_name=user.display_name,
            email_verified=user.email_verified_at is not None,
        )


class SessionResponse(BaseModel):
    user: UserSummary | None
    csrf_token: str | None = None


class MessageResponse(BaseModel):
    message: str

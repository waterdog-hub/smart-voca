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


class PasswordResetRequest(BaseModel):
    email: str = Field(max_length=MAX_REQUEST_EMAIL_LENGTH)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=MAX_MAIL_TOKEN_LENGTH)
    new_password: str = Field(max_length=MAX_REQUEST_PASSWORD_LENGTH)


class PasswordChangeRequest(BaseModel):
    # 비밀번호가 없는 소셜 전용 계정은 현재 값을 보내지 않는다 (D-M808)
    current_password: str = Field(default="", max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(max_length=MAX_REQUEST_PASSWORD_LENGTH)


class AccountDeleteRequest(BaseModel):
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class DisplayNameRequest(BaseModel):
    display_name: str = Field(max_length=MAX_REQUEST_NAME_LENGTH)


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


class MeResponse(UserSummary):
    has_password: bool
    social: list[str]  # 연결된 제공자 이름. 제공자 쪽 고유 번호는 응답에 넣지 않는다
    social_available: list[str]  # 지금 켜진 제공자 (키가 설정된 것)

    @classmethod
    def build(
        cls, user: User, social: list[str], social_available: list[str]
    ) -> "MeResponse":
        summary = UserSummary.from_user(user)
        return cls(
            **summary.model_dump(),
            has_password=user.password_hash is not None,
            social=social,
            social_available=social_available,
        )


class SocialCompleteRequest(BaseModel):
    email: str = Field(max_length=MAX_REQUEST_EMAIL_LENGTH)


class SocialLinkRequest(BaseModel):
    # 비밀번호가 있는 계정만 확인한다. 없으면 비워 둔다
    password: str = Field(default="", max_length=MAX_PASSWORD_LENGTH)


class SocialLinkResponse(BaseModel):
    authorize_url: str


class SessionResponse(BaseModel):
    user: UserSummary | None
    csrf_token: str | None = None


class MessageResponse(BaseModel):
    message: str

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 요청마다 쓰는 DB 세션, 로그인 확인, CSRF 확인, 세션 쿠키 처리
# 파일 위치: src/web/dependencies.py

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from web.errors import ApiError
from web.security.csrf import is_valid_csrf_token
from web.services.auth_service import AuthService, CurrentSession
from web.settings import Settings

SESSION_COOKIE_NAME = "sv_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
UNKNOWN_CLIENT_IP = "unknown"


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


def get_auth_service(request: Request, db: DbSession) -> AuthService:
    # 운영에서는 uvicorn의 프록시 헤더 설정이 있어야 이 값이 실제 사용자 IP가 된다 (M10)
    client_ip = request.client.host if request.client else UNKNOWN_CLIENT_IP
    return AuthService(db, request.app.state.settings, request.app.state.mailer, client_ip)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_optional_session(request: Request, service: AuthServiceDep) -> CurrentSession | None:
    return service.find_current_session(request.cookies.get(SESSION_COOKIE_NAME))


OptionalSession = Annotated[CurrentSession | None, Depends(get_optional_session)]


def require_login(current: OptionalSession) -> CurrentSession:
    if current is None:
        raise ApiError(401, "AUTH_REQUIRED", "로그인이 필요합니다.")
    return current


LoggedIn = Annotated[CurrentSession, Depends(require_login)]


def require_login_with_csrf(request: Request, current: LoggedIn) -> CurrentSession:
    submitted_token = request.headers.get(CSRF_HEADER_NAME)
    if not is_valid_csrf_token(current.session.csrf_token_hash, submitted_token):
        raise ApiError(403, "CSRF_INVALID", "요청을 확인할 수 없습니다. 새로고침해 주세요.")
    return current


LoggedInWrite = Annotated[CurrentSession, Depends(require_login_with_csrf)]


def require_verified_write(current: LoggedInWrite) -> CurrentSession:
    # M3부터 단어·설정·진도·시험의 쓰기 API가 이 조건을 쓴다 (API 설계 §1.1)
    if current.user.email_verified_at is None:
        raise ApiError(403, "EMAIL_NOT_VERIFIED", "이메일 인증이 필요합니다.")
    return current


VerifiedWrite = Annotated[CurrentSession, Depends(require_verified_write)]


def _uses_secure_cookie(settings: Settings) -> bool:
    # 개발 서버는 http로 실행하므로 Secure를 붙이면 쿠키가 전송되지 않는다
    return settings.is_production


def set_session_cookie(response: Response, session_token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=settings.session_ttl_absolute_days * 24 * 60 * 60,
        path="/",
        httponly=True,
        secure=_uses_secure_cookie(settings),
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_uses_secure_cookie(settings),
        samesite="lax",
    )

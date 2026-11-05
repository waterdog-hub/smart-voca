#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 가입, 로그인, 로그아웃, 세션 조회, 이메일 인증, 비밀번호 재설정 API (API 설계 §2)
# 파일 위치: src/web/routers/auth_api.py

from fastapi import APIRouter, Request, Response

from web.dependencies import (
    AccountServiceDep,
    SESSION_COOKIE_NAME,
    AuthServiceDep,
    LoggedInWrite,
    OptionalSession,
    clear_session_cookie,
    set_session_cookie,
)
from web.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    SessionResponse,
    SignupRequest,
    UserSummary,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 신규와 중복 가입의 응답이 달라지면 가입 여부가 드러나므로 문구를 하나로 둔다 (D-A04)
SIGNUP_ACCEPTED_MESSAGE = "입력한 이메일로 안내 메일을 보냈습니다. 메일을 확인해 주세요."


def _block_caching(response: Response) -> None:
    # 이메일과 CSRF 토큰이 담긴 응답을 브라우저나 프록시가 저장하지 못하게 한다
    response.headers["Cache-Control"] = "no-store"


@router.post("/signup", status_code=202)
def signup(payload: SignupRequest, service: AuthServiceDep) -> MessageResponse:
    service.signup(
        payload.email,
        payload.password,
        payload.display_name,
        payload.terms_agreed,
        payload.privacy_agreed,
    )
    return MessageResponse(message=SIGNUP_ACCEPTED_MESSAGE)


@router.post("/login")
def login(
    payload: LoginRequest, request: Request, response: Response, service: AuthServiceDep
) -> SessionResponse:
    result = service.login(
        payload.email, payload.password, request.cookies.get(SESSION_COOKIE_NAME)
    )
    set_session_cookie(response, result.session_token, service.settings)
    _block_caching(response)
    return SessionResponse(user=UserSummary.from_user(result.user), csrf_token=result.csrf_token)


@router.post("/logout", status_code=204)
def logout(current: LoggedInWrite, service: AuthServiceDep) -> Response:
    service.logout(current)
    response = Response(status_code=204)
    clear_session_cookie(response, service.settings)
    return response


@router.get("/session")
def read_session(
    request: Request, response: Response, current: OptionalSession, service: AuthServiceDep
) -> SessionResponse:
    _block_caching(response)
    if current is None:
        if SESSION_COOKIE_NAME in request.cookies:
            clear_session_cookie(response, service.settings)
        return SessionResponse(user=None)
    return SessionResponse(user=UserSummary.from_user(current.user), csrf_token=current.csrf_token)


@router.post("/logout-all", status_code=204)
def logout_all(current: LoggedInWrite, service: AccountServiceDep) -> Response:
    service.logout_all(current)
    response = Response(status_code=204)
    clear_session_cookie(response, service.settings)
    return response


# 가입 여부와 관계없이 같은 문구를 준다 (D-A04)
RESET_REQUEST_ACCEPTED_MESSAGE = "가입된 이메일이면 재설정 안내 메일을 보냈습니다. 메일을 확인해 주세요."


@router.post("/password-reset/request", status_code=202)
def request_password_reset(
    payload: PasswordResetRequest, service: AccountServiceDep
) -> MessageResponse:
    service.request_password_reset(payload.email)
    return MessageResponse(message=RESET_REQUEST_ACCEPTED_MESSAGE)


@router.post("/password-reset/confirm")
def confirm_password_reset(
    payload: PasswordResetConfirm, service: AccountServiceDep
) -> MessageResponse:
    service.confirm_password_reset(payload.token, payload.new_password)
    return MessageResponse(message="비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요.")


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest, service: AuthServiceDep) -> MessageResponse:
    service.verify_email(payload.token)
    return MessageResponse(message="이메일 인증이 완료되었습니다.")


@router.post("/resend-verification", status_code=202)
def resend_verification(current: LoggedInWrite, service: AuthServiceDep) -> MessageResponse:
    service.resend_verification(current.user)
    return MessageResponse(message="인증 메일을 보냈습니다. 메일을 확인해 주세요.")

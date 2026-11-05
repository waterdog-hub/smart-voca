#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 소셜 로그인 시작·콜백, 이메일 입력 가입, 계정 연결·해제 API (API 설계 §2, 이슈 #19)
# 파일 위치: src/web/routers/social_api.py

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from web.dependencies import (
    OAUTH_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AccountServiceDep,
    LoggedInWrite,
    SocialServiceDep,
    VerifiedWrite,
    clear_oauth_cookie,
    set_oauth_cookie,
    set_session_cookie,
)
from web.schemas.auth import (
    MessageResponse,
    SocialCompleteRequest,
    SocialLinkRequest,
    SocialLinkResponse,
)

router = APIRouter(prefix="/api/v1/auth/social", tags=["social"])

# 이미 가입된 이메일이어도 같은 문구를 준다 (D-A04)
COMPLETE_ACCEPTED_MESSAGE = "입력한 이메일로 안내 메일을 보냈습니다. 메일의 링크를 눌러 가입을 완료해 주세요."


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post("/complete", status_code=202)
def complete_signup(
    payload: SocialCompleteRequest, request: Request, service: SocialServiceDep
) -> MessageResponse:
    service.request_signup_mail(request.cookies.get(OAUTH_COOKIE_NAME), payload.email)
    return MessageResponse(message=COMPLETE_ACCEPTED_MESSAGE)


@router.get("/{provider}/start")
def start_login(provider: str, service: SocialServiceDep) -> Response:
    result = service.start(provider)
    response = RedirectResponse(result.authorize_url, status_code=302)
    set_oauth_cookie(response, result.pending_token, service.settings)
    _no_store(response)
    return response


@router.get("/{provider}/callback")
def callback(
    provider: str,
    request: Request,
    service: SocialServiceDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    result = service.handle_callback(
        provider,
        code,
        state,
        error,
        request.cookies.get(OAUTH_COOKIE_NAME),
        request.cookies.get(SESSION_COOKIE_NAME),
    )
    response = RedirectResponse(result.redirect, status_code=303)
    if result.session_token:
        set_session_cookie(response, result.session_token, service.settings)
    if not result.keep_pending_cookie:
        clear_oauth_cookie(response, service.settings)
    _no_store(response)
    return response


@router.post("/{provider}/link")
def start_link(
    provider: str,
    payload: SocialLinkRequest,
    current: LoggedInWrite,
    account: AccountServiceDep,
    service: SocialServiceDep,
) -> Response:
    # 하이재킹된 세션이 소셜 계정을 몰래 붙이지 못하게 비밀번호를 먼저 확인한다 (D-M807)
    account.confirm_password(current, payload.password)
    result = service.start(provider, link_user_id=current.user.id)
    body = SocialLinkResponse(authorize_url=result.authorize_url)
    response = Response(content=body.model_dump_json(), media_type="application/json")
    set_oauth_cookie(response, result.pending_token, service.settings)
    _no_store(response)
    return response


@router.delete("/{provider}", status_code=204)
def unlink(provider: str, current: VerifiedWrite, service: SocialServiceDep) -> Response:
    service.unlink(current.user, provider)
    return Response(status_code=204)

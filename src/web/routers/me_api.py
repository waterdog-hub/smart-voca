#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 내 정보, 표시 이름, 비밀번호 변경, 탈퇴 API (API 설계 §2, 이슈 #18)
# 파일 위치: src/web/routers/me_api.py

from fastapi import APIRouter, Response

from web.dependencies import (
    AccountServiceDep,
    LoggedIn,
    LoggedInWrite,
    VerifiedWrite,
    clear_session_cookie,
)
from web.schemas.auth import (
    AccountDeleteRequest,
    DisplayNameRequest,
    MessageResponse,
    PasswordChangeRequest,
    UserSummary,
)

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("")
def read_me(current: LoggedIn, response: Response) -> UserSummary:
    response.headers["Cache-Control"] = "no-store"
    return UserSummary.from_user(current.user)


@router.patch("")
def update_me(
    payload: DisplayNameRequest, current: VerifiedWrite, service: AccountServiceDep
) -> UserSummary:
    service.update_display_name(current, payload.display_name)
    return UserSummary.from_user(current.user)


# 비밀번호 변경과 탈퇴는 비밀번호를 다시 확인하므로 인증 전 회원도 쓸 수 있다 (이슈 #18)
@router.post("/password")
def change_password(
    payload: PasswordChangeRequest, current: LoggedInWrite, service: AccountServiceDep
) -> MessageResponse:
    service.change_password(current, payload.current_password, payload.new_password)
    return MessageResponse(message="비밀번호를 바꿨습니다. 다른 기기는 로그아웃되었습니다.")


# DELETE에 본문을 싣는 것을 막는 환경이 있어 POST로 둔다 (API 설계 D-API06과 같은 이유)
@router.post("/delete", status_code=204)
def delete_account(
    payload: AccountDeleteRequest, current: LoggedInWrite, service: AccountServiceDep
) -> Response:
    service.delete_account(current, payload.password)
    response = Response(status_code=204)
    clear_session_cookie(response, service.settings)
    return response

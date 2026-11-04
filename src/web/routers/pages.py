#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - Jinja2 화면 라우트 (P-02~P-05, 임시 홈, W-01~W-03)
# 파일 위치: src/web/routers/pages.py

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from web.dependencies import OptionalSession

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _render(request: Request, template_name: str, **context: object) -> Response:
    return templates.TemplateResponse(request, template_name, context)


def _render_member_page(
    request: Request, current: OptionalSession, template_name: str, title: str, page: str
) -> Response:
    if current is None:
        return RedirectResponse("/login", status_code=303)
    response = _render(
        request,
        template_name,
        title=title,
        page=page,
        display_name=current.user.display_name,
        email_verified=current.user.email_verified_at is not None,
    )
    # 뒤로 가기로 로그아웃 후의 회원 화면이 보이지 않게 한다
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/")
def home(request: Request, current: OptionalSession) -> Response:
    # H-01은 M5에서 만든다. 그때까지 로그인 결과를 확인하는 임시 화면이다 (이슈 #9)
    return _render_member_page(request, current, "home_temporary.html", "홈", "home")


@router.get("/words")
def words_page(request: Request, current: OptionalSession) -> Response:
    return _render_member_page(request, current, "words.html", "단어장", "words")


@router.get("/login")
def login_page(request: Request, current: OptionalSession) -> Response:
    if current is not None:
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", title="로그인", page="login")


@router.get("/signup")
def signup_page(request: Request, current: OptionalSession) -> Response:
    if current is not None:
        return RedirectResponse("/", status_code=303)
    return _render(request, "signup.html", title="가입", page="signup")


@router.get("/signup/sent")
def signup_sent_page(request: Request) -> Response:
    return _render(request, "signup_sent.html", title="인증 메일 안내", page="signup-sent")


@router.get("/verify-email")
def verify_email_page(request: Request) -> Response:
    # 토큰은 URL 조각에 있어 서버로 오지 않는다. 메일 검사 프로그램이 링크를 미리 열어도
    # 스크립트를 실행하지 않으면 토큰이 소비되지 않도록 화면의 스크립트가 POST로 보낸다
    return _render(request, "verify_email.html", title="이메일 인증", page="verify-email")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - Jinja2 화면 라우트 (P-02~P-05, H-01, W-01~W-03, M-01, M-02, S-01)
# 파일 위치: src/web/routers/pages.py

from pathlib import Path
from urllib.parse import urlencode

from config import ASSIGNED_TYPE_LABELS
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from web.dependencies import DbSession, OptionalSession
from web.repositories import plan_repository
from web.services.plan_service import PlanService
from web.services.setting_service import COUNT_FIELDS, DIRECTION_CHOICES, FORMAT_CHOICES

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _render(request: Request, template_name: str, **context: object) -> Response:
    return templates.TemplateResponse(request, template_name, context)


def _login_redirect(request: Request) -> Response:
    # 로그인 뒤 돌아올 주소를 남긴다 (화면 설계 §5.3). 주소 검사는 이동하는 쪽(auth.js)에서 한다
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    target = "/login" if path == "/" else f"/login?{urlencode({'next': path})}"
    return RedirectResponse(target, status_code=303)


def _selected_day(raw_day: str | None, days: list[tuple[int, int, int]], current_day: int) -> int:
    # 주소를 손으로 고쳐 없는 일차가 와도 오류 대신 현재 일차를 보여 준다
    if raw_day and raw_day.isascii() and raw_day.isdigit() and len(raw_day) < 10:
        if any(summary[0] == int(raw_day) for summary in days):
            return int(raw_day)
    return current_day


def _render_member_page(
    request: Request,
    current: OptionalSession,
    template_name: str,
    title: str,
    page: str,
    **context: object,
) -> Response:
    if current is None:
        return _login_redirect(request)
    response = _render(
        request,
        template_name,
        title=title,
        page=page,
        display_name=current.user.display_name,
        email_verified=current.user.email_verified_at is not None,
        **context,
    )
    # 뒤로 가기로 로그아웃 후의 회원 화면이 보이지 않게 한다
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/")
def home(request: Request, current: OptionalSession, db: DbSession) -> Response:
    progress = PlanService(db, current.user.id).progress() if current else None
    return _render_member_page(request, current, "home.html", "홈", "home", progress=progress)


@router.get("/memorize")
def memorize_page(request: Request, current: OptionalSession, db: DbSession) -> Response:
    if current is None:
        return _login_redirect(request)
    service = PlanService(db, current.user.id)
    current_day = service.current_day()
    days = service.list_days()
    selected_day = _selected_day(request.query_params.get("day"), days, current_day)
    return _render_member_page(
        request,
        current,
        "memorize.html",
        "암기",
        "memorize",
        days=days,
        current_day=current_day,
        selected_day=selected_day,
    )


@router.get("/plans")
def plans_page(request: Request, current: OptionalSession, db: DbSession) -> Response:
    if current is None:
        return _login_redirect(request)
    service = PlanService(db, current.user.id)
    days = service.list_days()
    selected_day = _selected_day(request.query_params.get("day"), days, service.current_day())
    rows = [
        {
            "word": word.word,
            "meaning": word.meaning,
            "type_label": ASSIGNED_TYPE_LABELS[item.assigned_type],
            "done": item.done,
        }
        for item, word in plan_repository.list_day_items(db, current.user.id, selected_day)
    ]
    return _render_member_page(
        request,
        current,
        "plans.html",
        "일차별 진도",
        "memorize",
        days=days,
        selected_day=selected_day,
        rows=rows,
    )


@router.get("/words")
def words_page(request: Request, current: OptionalSession) -> Response:
    return _render_member_page(request, current, "words.html", "단어장", "words")


@router.get("/settings")
def settings_page(request: Request, current: OptionalSession) -> Response:
    return _render_member_page(
        request,
        current,
        "settings.html",
        "설정",
        "settings",
        count_fields=COUNT_FIELDS,
        format_choices=FORMAT_CHOICES,
        direction_choices=DIRECTION_CHOICES,
    )


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

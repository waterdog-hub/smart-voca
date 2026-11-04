#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - Jinja2 화면 라우트 (P-01~P-05, H-01, W-01~W-03, M-01, M-02, T-01~T-03, R-01, S-01)
# 파일 위치: src/web/routers/pages.py

from pathlib import Path
from urllib.parse import urlencode

from config import ASSIGNED_TYPE_LABELS, TEST_DIRECTION_LABELS, TEST_FORMAT_LABELS
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from web.dependencies import DbSession, OptionalSession
from web.repositories import plan_repository, setting_repository, test_repository
from web.schemas.common import MAX_DB_INT
from web.services.plan_service import KOREA_TIME, PlanService
from web.services.setting_service import COUNT_FIELDS, DIRECTION_CHOICES, FORMAT_CHOICES
from web.services.test_service import (
    DEFAULT_QUESTION_COUNT,
    MAX_QUESTION_COUNT,
    MIN_QUESTION_COUNT,
    TestService,
    accuracy_percent,
    minimum_words,
)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _render(request: Request, template_name: str, **context: object) -> Response:
    context["demo_mode"] = request.app.state.settings.auto_verifies_email
    return templates.TemplateResponse(request, template_name, context)


HISTORY_PAGE_SIZE = 20
FORMAT_LABELS = {code: label for label, code in TEST_FORMAT_LABELS.items()}
DIRECTION_LABELS = {code: label for label, code in TEST_DIRECTION_LABELS.items()}


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


def _session_row(session: object) -> dict[str, object]:
    return {
        # 저장은 UTC, 표시는 한국 시간이다 (D-W11)
        "taken_at": session.taken_at.astimezone(KOREA_TIME).strftime("%Y-%m-%d %H:%M"),
        "format_label": FORMAT_LABELS[session.test_format],
        "direction_label": DIRECTION_LABELS[session.test_direction],
        "total": session.total,
        "score": session.score,
        "percent": accuracy_percent(session.score, session.total),
    }


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
    if current is None:
        return _render(request, "landing.html", title="smart-voca 시작하기", page="landing")
    latest = test_repository.list_sessions(db, current.user.id, limit=1, offset=0)
    return _render_member_page(
        request,
        current,
        "home.html",
        "홈",
        "home",
        progress=PlanService(db, current.user.id).progress(),
        latest_test=_session_row(latest[0]) if latest else None,
    )


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


@router.get("/tests")
def tests_page(request: Request, current: OptionalSession, db: DbSession) -> Response:
    if current is None:
        return _login_redirect(request)
    setting = setting_repository.get_settings(db, current.user.id)
    open_attempt = TestService(db, current.user.id).find_open_attempt()
    return _render_member_page(
        request,
        current,
        "tests.html",
        "시험",
        "tests",
        open_attempt_id=open_attempt.id if open_attempt else None,
        word_count=plan_repository.count_active_words(db, current.user.id),
        multiple_minimum=minimum_words("multiple"),
        format_choices=FORMAT_CHOICES,
        direction_choices=DIRECTION_CHOICES,
        default_format=setting.test_format,
        default_direction=setting.test_direction,
        min_count=MIN_QUESTION_COUNT,
        max_count=MAX_QUESTION_COUNT,
        default_count=DEFAULT_QUESTION_COUNT,
    )


# 경로가 {attempt_id}와 겹치지 않도록 고정 경로를 앞에 둔다
@router.get("/tests/history")
def test_history_page(request: Request, current: OptionalSession, db: DbSession) -> Response:
    if current is None:
        return _login_redirect(request)
    raw_page = request.query_params.get("page", "")
    # 주소를 손으로 고쳐 잘못된 쪽이 와도 오류 대신 첫 쪽을 보여 준다
    page = int(raw_page) if raw_page.isascii() and raw_page.isdigit() and len(raw_page) < 7 else 1
    page = max(page, 1)
    sessions, count, overall = TestService(db, current.user.id).history(
        HISTORY_PAGE_SIZE, (page - 1) * HISTORY_PAGE_SIZE
    )
    return _render_member_page(
        request,
        current,
        "test_history.html",
        "시험 기록",
        "test-history",
        rows=[_session_row(session) for session in sessions],
        total_count=count,
        overall_percent=overall,
        previous_page=page - 1 if page > 1 else None,
        next_page=page + 1 if page * HISTORY_PAGE_SIZE < count else None,
    )


@router.get("/tests/{attempt_id:int}")
def test_take_page(
    attempt_id: int, request: Request, current: OptionalSession, db: DbSession
) -> Response:
    if current is None:
        return _login_redirect(request)
    described = (
        TestService(db, current.user.id).describe_attempt(attempt_id)
        if attempt_id <= MAX_DB_INT
        else None
    )
    if described is None:
        raise HTTPException(status_code=404)
    status, session = described
    return _render_member_page(
        request,
        current,
        "test_take.html",
        "시험",
        "tests",
        attempt_id=attempt_id,
        status=status,
        session=session,
        percent=accuracy_percent(session.score, session.total) if session else 0,
    )


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
    title = "가입 안내" if request.app.state.settings.auto_verifies_email else "인증 메일 안내"
    return _render(request, "signup_sent.html", title=title, page="signup-sent")


@router.get("/verify-email")
def verify_email_page(request: Request) -> Response:
    # 토큰은 URL 조각에 있어 서버로 오지 않는다. 메일 검사 프로그램이 링크를 미리 열어도
    # 스크립트를 실행하지 않으면 토큰이 소비되지 않도록 화면의 스크립트가 POST로 보낸다
    return _render(request, "verify_email.html", title="이메일 인증", page="verify-email")

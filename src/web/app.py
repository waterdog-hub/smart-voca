#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - FastAPI 앱을 만들고 DB 연결과 라우터를 준비한다
# 파일 위치: src/web/app.py

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.db.base import check_database, make_engine, make_session_factory
from web.errors import register_error_handlers
from web.routers import (
    auth_api,
    health_api,
    me_api,
    social_api,
    pages,
    plans_api,
    settings_api,
    tests_api,
    wordbooks_api,
    words_api,
)
from web.services.mail_service import Mailer, create_mailer
from web.services.social_providers import SocialProvider, create_social_providers
from web.settings import Settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # DB에 연결할 수 없으면 요청을 받기 전에 시작을 멈춘다 (배포·운영 설계 §3.2)
    check_database(app.state.engine)
    yield
    app.state.engine.dispose()


def create_app(
    settings: Settings | None = None,
    mailer: Mailer | None = None,
    social_providers: dict[str, SocialProvider] | None = None,
) -> FastAPI:
    # uvicorn --factory로 실행한다. import만으로 설정을 읽지 않아 .env 없는 환경에서도 import할 수 있다
    app_settings = settings if settings is not None else Settings()

    if app_settings.is_public:
        # 인터넷에 열리는 환경에서는 API 구조를 공개하지 않는다 (D-API07, NFR-DEMO-03)
        app = FastAPI(
            title="smart-voca", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
        )
    else:
        app = FastAPI(title="smart-voca", lifespan=lifespan)

    app.state.settings = app_settings
    app.state.engine = make_engine(app_settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    # 테스트는 보낸 메일을 확인하려고 기록용 구현을 넘긴다
    app.state.mailer = mailer if mailer is not None else create_mailer(app_settings)
    # 키가 있는 제공자만 켠다. 테스트는 가짜 제공자를 넘긴다 (이슈 #19)
    app.state.social_providers = (
        social_providers if social_providers is not None else create_social_providers(app_settings)
    )

    register_error_handlers(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(health_api.router)
    app.include_router(auth_api.router)
    app.include_router(me_api.router)
    app.include_router(social_api.router)
    app.include_router(wordbooks_api.router)
    app.include_router(words_api.router)
    app.include_router(settings_api.router)
    app.include_router(plans_api.router)
    app.include_router(tests_api.router)
    app.include_router(pages.router)
    return app

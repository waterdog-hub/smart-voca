#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - FastAPI 앱을 만들고 DB 연결과 라우터를 준비한다
# 파일 위치: src/web/app.py

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from web.db.base import check_database, make_engine
from web.routers import health_api
from web.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # DB에 연결할 수 없으면 요청을 받기 전에 시작을 멈춘다 (배포·운영 설계 §3.2)
    check_database(app.state.engine)
    yield
    app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    # uvicorn --factory로 실행한다. import만으로 설정을 읽지 않아 .env 없는 환경에서도 import할 수 있다
    app_settings = settings if settings is not None else Settings()

    if app_settings.is_production:
        # 운영에서는 API 구조를 공개하지 않는다 (D-API07)
        app = FastAPI(
            title="smart-voca", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
        )
    else:
        app = FastAPI(title="smart-voca", lifespan=lifespan)

    app.state.engine = make_engine(app_settings.database_url)
    app.include_router(health_api.router)
    return app

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - FastAPI 앱을 만들고 라우터를 등록한다
# 파일 위치: src/web/app.py

from fastapi import FastAPI

from web.routers import health_api
from web.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    # 테스트가 환경변수를 바꾸지 않고 설정을 넘길 수 있도록 함수로 앱을 만든다
    app_settings = settings if settings is not None else Settings()

    if app_settings.is_production:
        # 운영에서는 API 구조를 공개하지 않는다 (D-API07)
        app = FastAPI(title="smart-voca", docs_url=None, redoc_url=None, openapi_url=None)
    else:
        app = FastAPI(title="smart-voca")

    app.include_router(health_api.router)
    return app


app = create_app()

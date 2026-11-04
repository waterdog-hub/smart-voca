#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 서비스와 DB 연결 상태 확인 엔드포인트
# 파일 위치: src/web/routers/health_api.py

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from web.db.base import check_database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/healthz")
def read_health(request: Request) -> JSONResponse:
    try:
        check_database(request.app.state.engine)
    except SQLAlchemyError:
        # 공개 주소이므로 응답에는 원인을 쓰지 않고 서버 로그에만 남긴다
        logger.exception("DB 연결 확인 실패")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 서비스 상태 확인 엔드포인트
# 파일 위치: src/web/routers/health_api.py

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def read_health() -> dict[str, str]:
    # DB 연결 확인과 실패 시 503은 DB가 생기는 M1에서 추가한다 (배포·운영 설계 §3)
    return {"status": "ok"}

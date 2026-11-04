#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 웹 테스트 공용 도우미 (테스트 클라이언트 생성)
# 파일 위치: tests/web_tests/support.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from web.app import create_app  # noqa: E402
from web.settings import Settings  # noqa: E402


def make_client(app_env: str = "local") -> TestClient:
    # 개발자의 .env가 결과를 바꾸지 않도록 .env를 읽지 않는다
    settings = Settings(app_env=app_env, _env_file=None)
    return TestClient(create_app(settings))

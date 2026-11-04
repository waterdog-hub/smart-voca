#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 웹 테스트 공용 도우미 (임시 DB, 테스트 클라이언트, 마이그레이션 설정)
# 파일 위치: tests/web_tests/support.py

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web.app import create_app  # noqa: E402
from web.settings import Settings  # noqa: E402


class WebTestCase(unittest.TestCase):
    """테스트마다 임시 폴더의 SQLite 파일을 쓴다. data/는 건드리지 않는다."""

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp_path = Path(temp_dir.name)
        self.database_url = f"sqlite:///{(self.temp_path / 'test.db').as_posix()}"

    def make_settings(self, app_env="local", database_url=None):
        # 개발자의 .env가 결과를 바꾸지 않도록 .env를 읽지 않는다
        return Settings(
            app_env=app_env, database_url=database_url or self.database_url, _env_file=None
        )

    def make_client(self, app_env="local"):
        client = TestClient(create_app(self.make_settings(app_env)))
        # with 문과 같은 동작이다. 앱 시작·종료 처리를 실행해 DB 연결을 닫는다
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def make_alembic_config(self):
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        # 설정 파일 문법에서 %는 특수 문자이므로 이스케이프한다
        config.set_main_option("sqlalchemy.url", self.database_url.replace("%", "%%"))
        config.attributes["configure_logging"] = False
        return config

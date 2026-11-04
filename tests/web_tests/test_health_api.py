#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 상태 확인, DB 연결 실패 처리, 환경별 API 문서 공개 여부 테스트
# 파일 위치: tests/web_tests/test_health_api.py

import logging
import os
import unittest
from unittest import mock

from web_tests.support import WebTestCase

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from web.app import create_app
from web.db.base import make_engine
from web.settings import Settings


class HealthApiTest(WebTestCase):
    def missing_database_url(self):
        return f"sqlite:///{(self.temp_path / 'missing' / 'test.db').as_posix()}"

    def test_healthz_returns_ok_when_database_connects(self):
        response = self.make_client().get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_healthz_returns_503_without_details_when_database_fails(self):
        client = self.make_client()
        working_engine = client.app.state.engine
        broken_engine = make_engine(self.missing_database_url())
        self.addCleanup(working_engine.dispose)
        self.addCleanup(broken_engine.dispose)
        client.app.state.engine = broken_engine
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        response = client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_app_does_not_start_when_database_fails(self):
        app = create_app(self.make_settings(database_url=self.missing_database_url()))
        with self.assertRaises(OperationalError):
            with TestClient(app):
                pass


class ApiDocsVisibilityTest(WebTestCase):
    def test_docs_open_in_local(self):
        client = self.make_client("local")
        self.assertEqual(client.get("/docs").status_code, 200)
        self.assertEqual(client.get("/openapi.json").status_code, 200)

    def test_docs_closed_in_production(self):
        client = self.make_client("production")
        for path in ("/docs", "/redoc", "/openapi.json"):
            self.assertEqual(client.get(path).status_code, 404, path)
        # 문서를 꺼도 상태 확인은 동작해야 한다
        self.assertEqual(client.get("/healthz").status_code, 200)


class SettingsTest(unittest.TestCase):
    def environment_without(self, *names):
        return {key: value for key, value in os.environ.items() if key not in names}

    def test_app_env_defaults_to_production(self):
        with mock.patch.dict(os.environ, self.environment_without("APP_ENV"), clear=True):
            settings = Settings(
                database_url="sqlite://",
                auth_hash_key="k" * 32,
                public_base_url="https://voca.example.test/",
                _env_file=None,
            )
        self.assertTrue(settings.is_production)
        self.assertEqual(settings.public_base_url, "https://voca.example.test")

    def test_production_requires_auth_hash_key(self):
        with mock.patch.dict(os.environ, self.environment_without("AUTH_HASH_KEY"), clear=True):
            with self.assertRaises(ValidationError):
                Settings(
                    app_env="production",
                    database_url="sqlite://",
                    public_base_url="https://voca.example.test",
                    _env_file=None,
                )

    def test_production_requires_https_public_base_url(self):
        for public_base_url in (None, "http://voca.example.test"):
            with self.assertRaises(ValidationError, msg=public_base_url):
                Settings(
                    app_env="production",
                    database_url="sqlite://",
                    auth_hash_key="k" * 32,
                    public_base_url=public_base_url,
                    _env_file=None,
                )

    def test_short_auth_hash_key_is_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(app_env="local", database_url="sqlite://", auth_hash_key="short", _env_file=None)

    def test_local_fills_development_defaults(self):
        names = ("AUTH_HASH_KEY", "PUBLIC_BASE_URL")
        with mock.patch.dict(os.environ, self.environment_without(*names), clear=True):
            settings = Settings(app_env="local", database_url="sqlite://", _env_file=None)
        self.assertEqual(settings.public_base_url, "http://127.0.0.1:8000")
        self.assertGreaterEqual(len(settings.auth_hash_key), 32)

    def test_missing_database_url_is_rejected(self):
        with mock.patch.dict(os.environ, self.environment_without("DATABASE_URL"), clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_empty_database_url_is_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(database_url="", _env_file=None)


if __name__ == "__main__":
    unittest.main()

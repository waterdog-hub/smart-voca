#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 상태 확인과 실행 환경별 API 문서 공개 여부 테스트
# 파일 위치: tests/web_tests/test_health_api.py

import os
import unittest
from unittest import mock

from web_tests.support import make_client

from web.settings import Settings


class HealthApiTest(unittest.TestCase):
    def test_healthz_returns_ok(self):
        response = make_client().get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class ApiDocsVisibilityTest(unittest.TestCase):
    def test_docs_open_in_local(self):
        client = make_client("local")
        self.assertEqual(client.get("/docs").status_code, 200)
        self.assertEqual(client.get("/openapi.json").status_code, 200)

    def test_docs_closed_in_production(self):
        client = make_client("production")
        for path in ("/docs", "/redoc", "/openapi.json"):
            self.assertEqual(client.get(path).status_code, 404, path)
        # 문서를 꺼도 상태 확인은 동작해야 한다
        self.assertEqual(client.get("/healthz").status_code, 200)


class SettingsDefaultTest(unittest.TestCase):
    def test_app_env_defaults_to_production(self):
        environment = {key: value for key, value in os.environ.items() if key != "APP_ENV"}
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertTrue(Settings(_env_file=None).is_production)


if __name__ == "__main__":
    unittest.main()

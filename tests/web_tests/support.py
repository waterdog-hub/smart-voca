#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 웹 테스트 공용 도우미 (임시 DB, 테스트 클라이언트, 메일 기록, 테스트 회원)
# 파일 위치: tests/web_tests/support.py

import re
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web.app import create_app  # noqa: E402
from web.db import tables  # noqa: E402,F401  (테이블을 메타데이터에 등록한다)
from web.db.base import Base, make_engine  # noqa: E402
from web.settings import Settings  # noqa: E402

TEST_AUTH_HASH_KEY = "test-auth-hash-key-at-least-32-characters"
TEST_PUBLIC_BASE_URL = "https://voca.example.test"
TEST_PASSWORD = "correct horse battery staple"
SIGNUP_API = "/api/v1/auth/signup"
LOGIN_API = "/api/v1/auth/login"
LOGOUT_API = "/api/v1/auth/logout"
SESSION_API = "/api/v1/auth/session"
VERIFY_API = "/api/v1/auth/verify-email"
RESEND_API = "/api/v1/auth/resend-verification"


class RecordingMailer:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)

    def last_token(self):
        return re.search(r"#token=(\S+)", self.messages[-1].body).group(1)


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
            app_env=app_env,
            database_url=database_url or self.database_url,
            auth_hash_key=TEST_AUTH_HASH_KEY,
            public_base_url=TEST_PUBLIC_BASE_URL,
            _env_file=None,
        )

    def make_client(self, app_env="local", mailer=None, ip="testclient"):
        app = create_app(self.make_settings(app_env), mailer=mailer)
        # 운영 쿠키에는 Secure가 붙어 https 주소로만 전송된다
        base_url = "https://testserver" if app_env == "production" else "http://testserver"
        client = TestClient(app, base_url=base_url, client=(ip, 50000))
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


class AuthTestCase(WebTestCase):
    """테이블을 만든 임시 DB에서 가입과 로그인을 쉽게 하도록 돕는다."""

    def setUp(self):
        super().setUp()
        engine = make_engine(self.database_url)
        Base.metadata.create_all(engine)
        engine.dispose()
        self.mailer = RecordingMailer()
        self.client = self.make_auth_client()

    def make_auth_client(self, ip="testclient"):
        return self.make_client(mailer=self.mailer, ip=ip)

    def signup_payload(self, email="learner@example.com", **overrides):
        return {
            "email": email,
            "password": TEST_PASSWORD,
            "display_name": "학습자",
            "terms_agreed": True,
            "privacy_agreed": True,
            **overrides,
        }

    def signup(self, email="learner@example.com", client=None):
        response = (client or self.client).post(SIGNUP_API, json=self.signup_payload(email))
        self.assertEqual(response.status_code, 202, response.text)
        return response

    def login(self, email="learner@example.com", password=TEST_PASSWORD, client=None):
        return (client or self.client).post(LOGIN_API, json={"email": email, "password": password})

    def signup_and_login(self, email="learner@example.com", client=None):
        self.signup(email, client=client)
        response = self.login(email, client=client)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def verified_member(self, email="learner@example.com", client=None):
        """인증까지 끝낸 회원을 만들고 쓰기 요청에 쓸 헤더를 돌려준다."""
        csrf_token = self.signup_and_login(email, client=client)
        self.verify_last_mail(client=client)
        return {"X-CSRF-Token": csrf_token}

    def verify_last_mail(self, client=None):
        response = (client or self.client).post(
            VERIFY_API, json={"token": self.mailer.last_token()}
        )
        self.assertEqual(response.status_code, 200, response.text)

    def db(self):
        return self.client.app.state.session_factory()

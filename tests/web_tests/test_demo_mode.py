#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시연 환경의 자동 인증과 보안 동작, 시작 화면 테스트 (NFR-DEMO-02, NFR-DEMO-03, D-W19)
# 파일 위치: tests/web_tests/test_demo_mode.py

import contextlib
import io
import os
import unittest
from datetime import timedelta
from unittest import mock

from web_tests.support import LOGIN_API, SIGNUP_API, AuthTestCase, RecordingMailer

from pydantic import ValidationError
from sqlalchemy import select

from web.db.tables import AuthToken, LoginAttempt, User
from web.services.mail_service import (
    ConsoleMailer,
    DiscardingMailer,
    MailMessage,
    UnconfiguredMailer,
    create_mailer,
)
from web.settings import Settings

WORDS_API = "/api/v1/words"


class DemoTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.demo = self.make_client(app_env="demo", mailer=self.mailer, ip="demo-member")

    def signup_demo(self, email="member@example.com"):
        return self.demo.post(SIGNUP_API, json=self.signup_payload(email))

    def login_demo(self, email="member@example.com"):
        return self.demo.post(LOGIN_API, json={"email": email, "password": "correct horse battery staple"})

    def stored_user(self, email="member@example.com"):
        with self.db() as db:
            return db.scalar(select(User).where(User.email == email))


class AutoVerifyTest(DemoTestCase):
    def test_signup_is_verified_at_once_without_mail_or_token(self):
        self.assertEqual(self.signup_demo().status_code, 202)
        self.assertIsNotNone(self.stored_user().email_verified_at)
        self.assertEqual(self.mailer.messages, [])
        with self.db() as db:
            self.assertEqual(db.scalars(select(AuthToken)).all(), [])

    def test_member_can_write_after_login(self):
        self.signup_demo()
        token = self.login_demo().json()["csrf_token"]
        response = self.demo.post(
            WORDS_API, json={"word": "apple", "meaning": "사과"}, headers={"X-CSRF-Token": token}
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_signup_does_not_log_in(self):
        # 자동 인증이어도 자동 로그인은 하지 않는다 (D-A04)
        response = self.signup_demo()
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(self.demo.get("/api/v1/progress").status_code, 401)

    def test_duplicate_signup_gets_same_response(self):
        first = self.signup_demo()
        # 같은 계정의 가입은 1분에 한 번이다. 제한이 지난 뒤를 재현한다
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(minutes=2)
            db.commit()
        second = self.signup_demo()
        self.assertEqual(second.status_code, first.status_code)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(self.mailer.messages[-1].subject, "[smart-voca] 이미 가입된 이메일입니다")

    def test_wrong_password_is_still_rejected(self):
        self.signup_demo()
        response = self.demo.post(LOGIN_API, json={"email": "member@example.com", "password": "wrong password value"})
        self.assertEqual(response.status_code, 401)


class OtherEnvironmentsDoNotAutoVerifyTest(AuthTestCase):
    def test_local_does_not_auto_verify(self):
        self.signup()
        self.assertIsNone(self.stored_email_verified_at())
        self.assertEqual(len(self.mailer.messages), 1)

    def test_production_does_not_auto_verify(self):
        client = self.make_client(app_env="production", mailer=RecordingMailer(), ip="production-member")
        self.signup(client=client)
        self.assertIsNone(self.stored_email_verified_at())

    def test_only_demo_setting_turns_it_on(self):
        for app_env, expected in (("local", False), ("demo", True), ("production", False)):
            with self.subTest(app_env=app_env):
                self.assertEqual(self.make_settings(app_env).auto_verifies_email, expected)

    def test_production_has_no_setting_that_turns_it_on(self):
        with mock.patch.dict(os.environ, {"AUTO_VERIFIES_EMAIL": "true", "AUTO_VERIFY": "true"}):
            settings = self.make_settings("production")
        self.assertFalse(settings.auto_verifies_email)

    def stored_email_verified_at(self):
        with self.db() as db:
            return db.scalar(select(User.email_verified_at))


class DemoSecurityTest(DemoTestCase):
    def test_api_docs_are_closed(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual(self.demo.get(path).status_code, 404)

    def test_session_cookie_is_secure(self):
        self.signup_demo()
        cookie = self.login_demo().headers["set-cookie"].lower()
        self.assertIn("secure", cookie)
        self.assertIn("httponly", cookie)

    def test_demo_requires_hash_key_and_https_address(self):
        environment = {k: v for k, v in os.environ.items() if k != "AUTH_HASH_KEY"}
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(ValidationError):
                Settings(app_env="demo", database_url="sqlite://",
                         public_base_url="https://demo.example.test", _env_file=None)
        for public_base_url in (None, "http://demo.example.test"):
            with self.subTest(public_base_url=public_base_url), self.assertRaises(ValidationError):
                Settings(app_env="demo", database_url="sqlite://", auth_hash_key="k" * 32,
                         public_base_url=public_base_url, _env_file=None)

    def test_unknown_environment_is_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(app_env="staging", database_url="sqlite://", _env_file=None)


class MailerChoiceTest(AuthTestCase):
    def test_each_environment_uses_its_mailer(self):
        self.assertIsInstance(create_mailer(self.make_settings("local")), ConsoleMailer)
        self.assertIsInstance(create_mailer(self.make_settings("demo")), DiscardingMailer)
        self.assertIsInstance(create_mailer(self.make_settings("production")), UnconfiguredMailer)

    def test_demo_mailer_prints_nothing(self):
        # 터널로 열린 서버의 콘솔과 로그에 링크를 남기지 않는다
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            DiscardingMailer().send(MailMessage("a@example.com", "제목", "본문"))
        self.assertEqual(output.getvalue(), "")


class DemoPagesTest(DemoTestCase):
    def test_public_pages_warn_not_to_use_real_password(self):
        for path in ("/", "/login", "/signup", "/signup/sent"):
            with self.subTest(path=path):
                html = self.demo.get(path).text
                self.assertIn('id="demo-notice"', html)
                self.assertIn("실제 비밀번호", html)

    def test_member_pages_warn_too(self):
        self.signup_demo()
        self.login_demo()
        self.assertIn('id="demo-notice"', self.demo.get("/").text)

    def test_local_pages_have_no_demo_notice(self):
        for path in ("/", "/login", "/signup"):
            with self.subTest(path=path):
                self.assertNotIn('id="demo-notice"', self.client.get(path).text)

    def test_signup_sent_guides_to_login_not_mail(self):
        html = self.demo.get("/signup/sent").text
        self.assertIn("로그인", html)
        self.assertNotIn("메일", html)
        self.assertIn("메일", self.client.get("/signup/sent").text)


class LandingPageTest(AuthTestCase):
    def test_anonymous_visitor_sees_landing(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-page="landing"', response.text)
        self.assertIn('href="/signup"', response.text)
        self.assertIn('href="/login"', response.text)
        self.assertNotIn("<script>", response.text)
        self.assertNotIn("logout-button", response.text)

    def test_member_sees_home_instead(self):
        self.signup_and_login()
        html = self.client.get("/").text
        self.assertNotIn('data-page="landing"', html)
        self.assertIn('id="logout-button"', html)


if __name__ == "__main__":
    unittest.main()

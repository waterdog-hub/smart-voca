#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - CSRF, 인증 완료 검사, 로그인 잠금, 정보 노출 방지 테스트
# 파일 위치: tests/web_tests/test_security.py

import json
import unittest
from datetime import timedelta

from web_tests.support import (
    LOGIN_API,
    LOGOUT_API,
    RESEND_API,
    SESSION_API,
    SIGNUP_API,
    TEST_AUTH_HASH_KEY,
    TEST_PASSWORD,
    VERIFY_API,
    AuthTestCase,
)

from fastapi import FastAPI
from sqlalchemy import select

from web.db.base import utc_now
from web.db.tables import AuthSession, LoginAttempt
from web.dependencies import VerifiedWrite
from web.security import rate_limit
from web.security.tokens import keyed_hash
from web.services.mail_service import MailSendError, UnconfiguredMailer

WRITE_PROBE_API = "/api/v1/probe-write"
WRONG_PASSWORD = "wrong password here"


def add_write_probe_route(app: FastAPI) -> None:
    # M3 전에는 인증 완료를 요구하는 API가 없어 같은 조건의 시험용 주소를 붙인다
    @app.post(WRITE_PROBE_API)
    def write_probe(current: VerifiedWrite) -> dict[str, str]:
        return {"email": current.user.email}


class CsrfTest(AuthTestCase):
    def assert_csrf_rejected(self, headers):
        response = self.client.post(LOGOUT_API, headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")
        self.assertIsNotNone(self.client.get(SESSION_API).json()["user"])

    def test_missing_token_is_rejected(self):
        self.signup_and_login()
        self.assert_csrf_rejected({})

    def test_wrong_token_is_rejected(self):
        self.signup_and_login()
        self.assert_csrf_rejected({"X-CSRF-Token": "wrong"})

    def test_other_session_token_is_rejected(self):
        other_device = self.make_auth_client()
        self.signup_and_login()
        other_token = self.login(client=other_device).json()["csrf_token"]
        self.assert_csrf_rejected({"X-CSRF-Token": other_token})

    def test_session_cookie_cannot_be_used_as_token(self):
        self.signup_and_login()
        self.assert_csrf_rejected({"X-CSRF-Token": self.client.cookies["sv_session"]})

    def test_token_is_not_stored_in_plain_text(self):
        csrf_token = self.signup_and_login()
        with self.db() as db:
            self.assertNotEqual(db.scalar(select(AuthSession)).csrf_token_hash, csrf_token)

    def test_resend_also_requires_token(self):
        self.signup_and_login()
        self.assertEqual(self.client.post(RESEND_API).status_code, 403)


class CrossSiteJsonOnlyTest(AuthTestCase):
    """토큰이 없는 공개 POST는 JSON만 받아, 다른 사이트의 폼 전송을 막는다."""

    def test_public_posts_reject_form_style_content_types(self):
        self.signup()
        requests = [
            (LOGIN_API, {"email": "learner@example.com", "password": TEST_PASSWORD}),
            (SIGNUP_API, self.signup_payload("other@example.com")),
            (VERIFY_API, {"token": self.mailer.last_token()}),
        ]
        for content_type in ("text/plain", "application/x-www-form-urlencoded"):
            for url, payload in requests:
                with self.subTest(url=url, content_type=content_type):
                    response = self.client.post(
                        url, content=json.dumps(payload), headers={"Content-Type": content_type}
                    )
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertEqual(response.json()["error"]["code"], "VALIDATION_FAILED")
        self.assertNotIn("sv_session", self.client.cookies)


class VerifiedWriteTest(AuthTestCase):
    def setUp(self):
        super().setUp()
        add_write_probe_route(self.client.app)

    def test_anonymous_write_returns_401(self):
        response = self.client.post(WRITE_PROBE_API)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_unverified_write_returns_403(self):
        csrf_token = self.signup_and_login()
        response = self.client.post(WRITE_PROBE_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "EMAIL_NOT_VERIFIED")

    def test_verified_write_without_csrf_returns_403(self):
        self.signup_and_login()
        self.verify_last_mail()
        response = self.client.post(WRITE_PROBE_API)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")

    def test_verified_write_is_allowed(self):
        csrf_token = self.signup_and_login()
        self.verify_last_mail()
        response = self.client.post(WRITE_PROBE_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"email": "learner@example.com"})


class LoginLockTest(AuthTestCase):
    def fail_login(self, times, email="learner@example.com", client=None):
        for _ in range(times):
            response = self.login(email, WRONG_PASSWORD, client=client)
            self.assertEqual(response.status_code, 401, response.text)

    def age_attempts(self, delta):
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= delta
            db.commit()

    def assert_locked(self, response):
        self.assertEqual(response.status_code, 429)
        error = response.json()["error"]
        self.assertEqual(error["code"], "RATE_LIMITED")
        self.assertGreater(error["retry_after"], 0)
        self.assertLessEqual(error["retry_after"], 15 * 60)
        self.assertEqual(response.headers["retry-after"], str(error["retry_after"]))

    def test_four_failures_do_not_lock(self):
        self.signup()
        self.fail_login(4)
        self.assertEqual(self.login().status_code, 200)

    def test_fifth_failure_locks_even_correct_password(self):
        self.signup()
        self.fail_login(5)
        self.assert_locked(self.login(password=WRONG_PASSWORD))
        self.assert_locked(self.login())

    def test_other_ip_is_not_locked(self):
        self.signup()
        self.fail_login(5)
        victim_device = self.make_auth_client(ip="10.0.0.2")
        self.assertEqual(self.login(client=victim_device).status_code, 200)

    def test_other_account_on_same_ip_is_not_locked(self):
        self.signup()
        self.fail_login(5)
        self.signup("second@example.com")
        self.assertEqual(self.login("second@example.com").status_code, 200)

    def test_lock_ends_after_fifteen_minutes(self):
        self.signup()
        self.fail_login(5)
        self.age_attempts(timedelta(minutes=14, seconds=50))
        self.assert_locked(self.login())
        self.age_attempts(timedelta(seconds=11))
        self.assertEqual(self.login().status_code, 200)

    def test_unknown_email_locks_the_same_way(self):
        self.fail_login(5, "nobody@example.com")
        self.assert_locked(self.login("nobody@example.com"))

    def test_email_case_does_not_bypass_lock(self):
        self.signup()
        self.fail_login(3)
        self.fail_login(2, "LEARNER@EXAMPLE.COM")
        self.assert_locked(self.login("Learner@Example.com"))

    def test_success_clears_only_that_account_login_failures(self):
        self.signup()
        self.signup("second@example.com")
        self.fail_login(4)
        self.fail_login(2, "second@example.com")
        self.assertEqual(self.login().status_code, 200)
        self.fail_login(4)
        self.assertEqual(self.login().status_code, 200)
        with self.db() as db:
            login_rows = db.scalars(
                select(LoginAttempt).where(LoginAttempt.action == rate_limit.ACTION_LOGIN)
            ).all()
        self.assertEqual(len(login_rows), 2)

    def add_attempts_from_ip(self, ip, action, count):
        now = utc_now()
        ip_hash = keyed_hash(TEST_AUTH_HASH_KEY, ip)
        with self.db() as db:
            for index in range(count):
                db.add(
                    LoginAttempt(
                        account_key_hash=keyed_hash(TEST_AUTH_HASH_KEY, f"user{index}"),
                        ip_hash=ip_hash,
                        action=action,
                        created_at=now,
                    )
                )
            db.commit()

    def test_many_failures_from_one_ip_are_limited(self):
        self.signup()
        self.add_attempts_from_ip("testclient", rate_limit.ACTION_LOGIN, 49)
        self.assertEqual(self.login("spray@example.com", WRONG_PASSWORD).status_code, 401)
        self.assert_locked(self.login("another@example.com", WRONG_PASSWORD))

    def test_many_signups_from_one_ip_are_limited(self):
        self.add_attempts_from_ip("testclient", rate_limit.ACTION_SIGNUP, 20)
        response = self.client.post(SIGNUP_API, json=self.signup_payload())
        self.assert_locked_signup(response)
        self.assertEqual(self.mailer.messages, [])

    def assert_locked_signup(self, response):
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "RATE_LIMITED")

    def test_same_email_signup_is_limited_for_a_minute_from_any_ip(self):
        self.signup()
        other_ip = self.make_auth_client(ip="10.0.0.2")
        self.assert_locked_signup(other_ip.post(SIGNUP_API, json=self.signup_payload()))
        self.age_attempts(timedelta(seconds=61))
        self.signup(client=other_ip)

    def test_nearby_signups_from_shared_ip_are_allowed(self):
        self.signup("first@example.com")
        self.signup("second@example.com")

    def test_attempt_records_hold_no_plain_email_or_ip(self):
        self.signup()
        self.fail_login(1)
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                self.assertNotIn("learner", attempt.account_key_hash)
                self.assertNotIn("testclient", attempt.ip_hash)
                self.assertEqual(len(attempt.account_key_hash), 64)
                self.assertEqual(len(attempt.ip_hash), 64)


class FailingMailer:
    def send(self, message):
        raise MailSendError("시험용 실패")


class MailFailureTest(AuthTestCase):
    def test_signup_response_is_unchanged_when_mail_fails(self):
        client = self.make_client(mailer=FailingMailer())
        with self.assertLogs("web.services.auth_service", level="ERROR"):
            response = client.post(SIGNUP_API, json=self.signup_payload())
        self.assertEqual(response.status_code, 202)

    def test_resend_reports_mail_failure_and_allows_login(self):
        client = self.make_client(mailer=FailingMailer())
        with self.assertLogs("web.services.auth_service", level="ERROR"):
            client.post(SIGNUP_API, json=self.signup_payload())
        csrf_token = self.login(client=client).json()["csrf_token"]
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(seconds=61)
            db.commit()
        with self.assertLogs("web.services.auth_service", level="ERROR"):
            response = client.post(RESEND_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "MAIL_SEND_FAILED")

    def test_production_does_not_use_console_mailer(self):
        production = self.make_client("production")
        self.assertIsInstance(production.app.state.mailer, UnconfiguredMailer)


class InformationLeakTest(AuthTestCase):
    def test_validation_error_does_not_echo_input(self):
        secret = "my-very-secret-password"
        response = self.client.post(
            SIGNUP_API, json={"email": 123, "password": secret, "display_name": ["x"]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(secret, response.text)
        error = response.json()["error"]
        self.assertEqual(error["code"], "VALIDATION_FAILED")
        for field in ("email", "display_name", "terms_agreed", "privacy_agreed"):
            self.assertIn(field, error["fields"])

    def test_overlong_login_password_is_rejected_without_hashing(self):
        response = self.client.post(
            LOGIN_API, json={"email": "learner@example.com", "password": "x" * 129}
        )
        self.assertEqual(response.status_code, 400)

    def test_broken_json_returns_design_format(self):
        response = self.client.post(
            LOGIN_API, content="{broken", headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_FAILED")

    def test_unknown_api_path_returns_design_format(self):
        response = self.client.get("/api/v1/nothing-here")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    def test_wrong_method_returns_design_format(self):
        response = self.client.get(LOGIN_API)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_logs_do_not_contain_secrets(self):
        with self.assertLogs("web", level="INFO") as captured:
            self.signup()
            token = self.mailer.last_token()
            self.login(password=WRONG_PASSWORD)
            self.login()
            session_token = self.client.cookies["sv_session"]
            self.verify_last_mail()
        log_text = "\n".join(captured.output)
        for secret in (TEST_PASSWORD, WRONG_PASSWORD, token, session_token, "learner@example.com"):
            self.assertNotIn(secret, log_text)


if __name__ == "__main__":
    unittest.main()

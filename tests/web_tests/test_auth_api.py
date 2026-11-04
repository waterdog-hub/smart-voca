#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 가입, 이메일 인증, 로그인, 세션, 로그아웃 API 테스트
# 파일 위치: tests/web_tests/test_auth_api.py

import unittest
from datetime import timedelta

from web_tests.support import (
    LOGOUT_API,
    RESEND_API,
    SESSION_API,
    SIGNUP_API,
    TEST_PASSWORD,
    VERIFY_API,
    AuthTestCase,
)

from sqlalchemy import select

from web.db.base import utc_now
from web.db.tables import AuthSession, AuthToken, LoginAttempt, User, UserSetting
from web.security.tokens import generate_token, hash_token


class SignupTest(AuthTestCase):
    def test_signup_creates_user_settings_and_verification_mail(self):
        response = self.signup()
        self.assertNotIn("set-cookie", response.headers)
        with self.db() as db:
            user = db.scalar(select(User))
            self.assertEqual(user.email, "learner@example.com")
            self.assertTrue(user.password_hash.startswith("$argon2id$"))
            self.assertIsNone(user.email_verified_at)
            self.assertIsNotNone(user.terms_agreed_at)
            self.assertIsNotNone(user.privacy_agreed_at)
            self.assertIsNotNone(db.get(UserSetting, user.id))
        self.assertEqual(self.mailer.messages[0].recipient, "learner@example.com")
        self.assertIn(
            "https://voca.example.test/verify-email#token=", self.mailer.messages[0].body
        )

    def test_duplicate_signup_gives_same_response_and_sends_notice(self):
        first = self.signup()
        other_client = self.make_auth_client(ip="10.0.0.2")
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(minutes=2)
            db.commit()
        second = self.signup(client=other_client)
        self.assertEqual(first.json(), second.json())
        self.assertNotIn("set-cookie", second.headers)
        self.assertEqual(len(self.mailer.messages), 2)
        self.assertNotIn("#token=", self.mailer.messages[1].body)
        self.assertIn("이미 가입", self.mailer.messages[1].subject)
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(User)).all()), 1)

    def test_email_is_normalized(self):
        self.signup("  Learner@Example.COM ")
        with self.db() as db:
            self.assertEqual(db.scalar(select(User)).email, "learner@example.com")
        self.assertEqual(self.login("LEARNER@example.com").status_code, 200)

    def test_invalid_input_returns_fields(self):
        cases = [
            ({"email": "not-an-email"}, "email"),
            ({"email": "a@b"}, "email"),
            ({"email": f"{'a' * 250}@example.com"}, "email"),
            ({"password": "short"}, "password"),
            ({"password": "x" * 129}, "password"),
            ({"password": "PassWord123"}, "password"),
            ({"password": "my learner@example.COM pw"}, "password"),
            ({"display_name": "   "}, "display_name"),
            ({"display_name": "x" * 101}, "display_name"),
            ({"display_name": "a\u0000b"}, "display_name"),
            ({"terms_agreed": False}, "terms_agreed"),
            ({"privacy_agreed": False}, "privacy_agreed"),
        ]
        for overrides, field in cases:
            with self.subTest(field=field, overrides=str(overrides)[:40]):
                response = self.client.post(SIGNUP_API, json=self.signup_payload(**overrides))
                self.assertEqual(response.status_code, 400)
                error = response.json()["error"]
                self.assertEqual(error["code"], "VALIDATION_FAILED")
                self.assertIn(field, error["fields"])
        with self.db() as db:
            self.assertEqual(db.scalars(select(User)).all(), [])
            # 입력 오류는 횟수 제한을 쓰지 않는다. 잘못 입력했다고 1분을 기다릴 필요가 없다
            self.assertEqual(db.scalars(select(LoginAttempt)).all(), [])

    def test_password_length_boundaries_are_accepted(self):
        for index, length in enumerate((8, 128)):
            payload = self.signup_payload(f"user{index}@example.com", password="k7!mQz#p" * 16)
            payload["password"] = payload["password"][:length]
            response = self.client.post(SIGNUP_API, json=payload)
            self.assertEqual(response.status_code, 202, response.text)


class VerifyEmailTest(AuthTestCase):
    def age_token(self, delta):
        with self.db() as db:
            token = db.scalar(select(AuthToken))
            token.expires_at -= delta
            db.commit()

    def test_valid_link_marks_user_verified(self):
        self.signup()
        self.verify_last_mail()
        with self.db() as db:
            self.assertIsNotNone(db.scalar(select(User)).email_verified_at)
            self.assertIsNotNone(db.scalar(select(AuthToken)).used_at)

    def test_token_is_stored_only_as_hash(self):
        self.signup()
        raw_token = self.mailer.last_token()
        with self.db() as db:
            stored = db.scalar(select(AuthToken))
        self.assertNotEqual(stored.token_hash, raw_token)
        self.assertEqual(stored.token_hash, hash_token(raw_token))
        self.assertAlmostEqual(
            stored.expires_at, utc_now() + timedelta(hours=24), delta=timedelta(minutes=1)
        )

    def assert_token_rejected(self, token):
        response = self.client.post(VERIFY_API, json={"token": token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "TOKEN_INVALID")

    def test_reused_link_is_rejected(self):
        self.signup()
        self.verify_last_mail()
        self.assert_token_rejected(self.mailer.last_token())

    def test_expired_link_is_rejected(self):
        self.signup()
        self.age_token(timedelta(hours=25))
        self.assert_token_rejected(self.mailer.last_token())
        with self.db() as db:
            self.assertIsNone(db.scalar(select(User)).email_verified_at)

    def test_unknown_link_is_rejected(self):
        self.assert_token_rejected(generate_token())

    def test_reset_password_token_cannot_verify_email(self):
        self.signup()
        with self.db() as db:
            db.scalar(select(AuthToken)).purpose = "reset_password"
            db.commit()
        self.assert_token_rejected(self.mailer.last_token())


class ResendVerificationTest(AuthTestCase):
    def pass_mail_limit(self):
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(seconds=61)
            db.commit()

    def test_resend_requires_login(self):
        response = self.client.post(RESEND_API)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_resend_right_after_signup_is_limited(self):
        csrf_token = self.signup_and_login()
        response = self.client.post(RESEND_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "RATE_LIMITED")
        self.assertGreater(response.json()["error"]["retry_after"], 0)
        self.assertEqual(len(self.mailer.messages), 1)

    def test_resend_sends_new_link_and_invalidates_old_one(self):
        csrf_token = self.signup_and_login()
        old_token = self.mailer.last_token()
        self.pass_mail_limit()
        response = self.client.post(RESEND_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(self.mailer.messages), 2)
        self.assertNotEqual(self.mailer.last_token(), old_token)
        rejected = self.client.post(VERIFY_API, json={"token": old_token})
        self.assertEqual(rejected.status_code, 400)
        self.verify_last_mail()

    def test_second_resend_within_a_minute_is_limited(self):
        csrf_token = self.signup_and_login()
        self.pass_mail_limit()
        headers = {"X-CSRF-Token": csrf_token}
        self.assertEqual(self.client.post(RESEND_API, headers=headers).status_code, 202)
        self.assertEqual(self.client.post(RESEND_API, headers=headers).status_code, 429)

    def test_verified_user_gets_no_new_mail(self):
        csrf_token = self.signup_and_login()
        self.verify_last_mail()
        self.pass_mail_limit()
        response = self.client.post(RESEND_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(self.mailer.messages), 1)


class LoginTest(AuthTestCase):
    def test_login_sets_protected_cookie_and_returns_user(self):
        self.signup()
        response = self.login()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["user"],
            {"email": "learner@example.com", "display_name": "학습자", "email_verified": False},
        )
        self.assertTrue(body["csrf_token"])
        cookie = response.headers["set-cookie"].lower()
        self.assertTrue(cookie.startswith("sv_session="))
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("path=/", cookie)
        self.assertIn(f"max-age={14 * 24 * 60 * 60}", cookie)
        self.assertNotIn("secure", cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_production_cookie_is_secure(self):
        production = self.make_client("production", mailer=self.mailer)
        self.signup(client=production)
        cookie = self.login(client=production).headers["set-cookie"].lower()
        self.assertIn("secure", cookie)
        self.assertEqual(production.get(SESSION_API).json()["user"]["email"], "learner@example.com")

    def test_session_token_is_stored_only_as_hash(self):
        self.signup()
        self.login()
        raw_token = self.client.cookies["sv_session"]
        with self.db() as db:
            session = db.scalar(select(AuthSession))
        self.assertEqual(session.token_hash, hash_token(raw_token))
        self.assertNotEqual(session.token_hash, raw_token)

    def test_wrong_password_and_unknown_email_look_the_same(self):
        self.signup()
        wrong_password = self.login(password="wrong password here")
        unknown_email = self.login("nobody@example.com")
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(wrong_password.json(), unknown_email.json())
        self.assertEqual(wrong_password.json()["error"]["code"], "LOGIN_FAILED")
        self.assertNotIn("set-cookie", wrong_password.headers)

    def test_social_only_account_cannot_login_with_password(self):
        self.signup()
        with self.db() as db:
            db.scalar(select(User)).password_hash = None
            db.commit()
        self.assertEqual(self.login().status_code, 401)

    def test_new_login_replaces_previous_session_on_same_browser(self):
        self.signup()
        self.login()
        first_token = self.client.cookies["sv_session"]
        self.login()
        self.assertNotEqual(self.client.cookies["sv_session"], first_token)
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(AuthSession)).all()), 1)

    def test_other_devices_keep_their_sessions(self):
        self.signup()
        other_device = self.make_auth_client()
        self.login()
        self.login(client=other_device)
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(AuthSession)).all()), 2)

    def test_login_removes_expired_rows(self):
        self.signup()
        self.login()
        with self.db() as db:
            db.scalar(select(AuthSession)).expires_at = utc_now() - timedelta(seconds=1)
            db.scalar(select(AuthToken)).expires_at = utc_now() - timedelta(seconds=1)
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at = utc_now() - timedelta(days=31)
            db.commit()
        self.client.cookies.clear()
        self.login()
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(AuthSession)).all()), 1)
            self.assertEqual(db.scalars(select(AuthToken)).all(), [])
            self.assertEqual(db.scalars(select(LoginAttempt)).all(), [])


class SessionTest(AuthTestCase):
    def update_session(self, **changes):
        with self.db() as db:
            session = db.scalar(select(AuthSession))
            for name, value in changes.items():
                setattr(session, name, value)
            db.commit()

    def test_anonymous_session_is_empty(self):
        response = self.client.get(SESSION_API)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user": None, "csrf_token": None})
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_session_returns_same_csrf_token_as_login(self):
        csrf_token = self.signup_and_login()
        body = self.client.get(SESSION_API).json()
        self.assertEqual(body["csrf_token"], csrf_token)
        self.assertEqual(body["user"]["email"], "learner@example.com")
        self.assertNotIn("id", body["user"])

    def test_verification_is_reflected_in_active_session(self):
        self.signup_and_login()
        self.assertFalse(self.client.get(SESSION_API).json()["user"]["email_verified"])
        self.verify_last_mail()
        self.assertTrue(self.client.get(SESSION_API).json()["user"]["email_verified"])

    def assert_session_expired(self):
        response = self.client.get(SESSION_API)
        self.assertIsNone(response.json()["user"])
        self.assertIn("sv_session", response.headers.get("set-cookie", ""))
        with self.db() as db:
            self.assertEqual(db.scalars(select(AuthSession)).all(), [])

    def test_idle_session_expires_after_three_days(self):
        self.signup_and_login()
        self.update_session(last_seen_at=utc_now() - timedelta(days=3, seconds=1))
        self.assert_session_expired()

    def test_session_expires_at_absolute_limit_even_when_active(self):
        self.signup_and_login()
        self.update_session(expires_at=utc_now() - timedelta(seconds=1))
        self.assert_session_expired()

    def test_absolute_limit_is_fourteen_days(self):
        self.signup_and_login()
        with self.db() as db:
            session = db.scalar(select(AuthSession))
        self.assertEqual(session.expires_at - session.created_at, timedelta(days=14))

    def test_activity_extends_idle_limit(self):
        self.signup_and_login()
        old_seen = utc_now() - timedelta(days=2)
        self.update_session(last_seen_at=old_seen)
        self.assertIsNotNone(self.client.get(SESSION_API).json()["user"])
        with self.db() as db:
            self.assertGreater(db.scalar(select(AuthSession)).last_seen_at, old_seen)

    def test_recent_activity_is_not_written_again(self):
        self.signup_and_login()
        recent_seen = utc_now() - timedelta(seconds=10)
        self.update_session(last_seen_at=recent_seen)
        self.client.get(SESSION_API)
        with self.db() as db:
            self.assertEqual(db.scalar(select(AuthSession)).last_seen_at, recent_seen)

    def test_unknown_cookie_is_cleared(self):
        self.client.cookies.set("sv_session", generate_token())
        response = self.client.get(SESSION_API)
        self.assertIsNone(response.json()["user"])
        self.assertIn("sv_session", response.headers["set-cookie"])

    def test_pending_signup_session_is_not_a_login(self):
        token = generate_token()
        with self.db() as db:
            db.add(
                AuthSession(
                    token_hash=hash_token(token),
                    csrf_token_hash=hash_token("unused"),
                    expires_at=utc_now() + timedelta(hours=1),
                    pending_provider="kakao",
                    pending_provider_user_id="123",
                )
            )
            db.commit()
        self.client.cookies.set("sv_session", token)
        self.assertIsNone(self.client.get(SESSION_API).json()["user"])


class LogoutTest(AuthTestCase):
    def test_logout_ends_only_current_session(self):
        csrf_token = self.signup_and_login()
        other_device = self.make_auth_client()
        self.login(client=other_device)
        response = self.client.post(LOGOUT_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 204)
        self.assertIn("sv_session", response.headers["set-cookie"])
        self.assertIsNone(self.client.get(SESSION_API).json()["user"])
        self.assertIsNotNone(other_device.get(SESSION_API).json()["user"])

    def test_old_cookie_does_not_work_after_logout(self):
        csrf_token = self.signup_and_login()
        old_cookie = self.client.cookies["sv_session"]
        self.client.post(LOGOUT_API, headers={"X-CSRF-Token": csrf_token})
        self.client.cookies.set("sv_session", old_cookie)
        self.assertIsNone(self.client.get(SESSION_API).json()["user"])

    def test_logout_without_login_is_rejected(self):
        response = self.client.post(LOGOUT_API)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_login_works_again_after_logout(self):
        csrf_token = self.signup_and_login()
        self.client.post(LOGOUT_API, headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(self.login(password=TEST_PASSWORD).status_code, 200)


if __name__ == "__main__":
    unittest.main()

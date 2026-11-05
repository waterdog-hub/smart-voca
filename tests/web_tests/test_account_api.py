#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 비밀번호 재설정·변경, 표시 이름, 모든 기기 로그아웃, 탈퇴 API와 화면 테스트 (FR-AUTH-10~14)
# 파일 위치: tests/web_tests/test_account_api.py

import unittest
from datetime import timedelta

from web_tests.support import SESSION_API, TEST_PASSWORD, AuthTestCase

from sqlalchemy import select

from web.db.base import utc_now
from web.db.tables import AuthSession, AuthToken, LoginAttempt, User, Word
from web.services.mail_service import MailSendError

RESET_REQUEST_API = "/api/v1/auth/password-reset/request"
RESET_CONFIRM_API = "/api/v1/auth/password-reset/confirm"
LOGOUT_ALL_API = "/api/v1/auth/logout-all"
ME_API = "/api/v1/me"
PASSWORD_API = "/api/v1/me/password"
DELETE_API = "/api/v1/me/delete"
NEW_PASSWORD = "another long passphrase 42"
EMAIL = "learner@example.com"


class FailingMailer:
    def send(self, message):
        raise MailSendError("실패")


class ResetRequestTest(AuthTestCase):
    def request_reset(self, email=EMAIL, client=None):
        return (client or self.client).post(RESET_REQUEST_API, json={"email": email})

    def test_registered_email_gets_a_reset_link(self):
        self.signup()
        self.mailer.messages.clear()
        response = self.request_reset()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(self.mailer.messages), 1)
        message = self.mailer.messages[0]
        self.assertEqual(message.recipient, EMAIL)
        self.assertIn("https://voca.example.test/reset-password#token=", message.body)

    def test_unknown_email_looks_the_same_and_sends_nothing(self):
        self.signup()
        self.mailer.messages.clear()
        known = self.request_reset()
        unknown = self.request_reset("nobody@example.com")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(len(self.mailer.messages), 1)

    def test_malformed_email_is_rejected_with_a_field_message(self):
        response = self.request_reset("not-an-email")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["error"]["fields"])

    def test_fourth_request_in_an_hour_is_limited_even_for_unknown_email(self):
        for email in (EMAIL, "nobody@example.com"):
            for _ in range(3):
                self.assertEqual(self.request_reset(email).status_code, 202)
            blocked = self.request_reset(email)
            self.assertEqual(blocked.status_code, 429)
            self.assertIn("retry-after", blocked.headers)

    def test_ip_limit_applies_across_accounts(self):
        for number in range(20):
            self.assertEqual(self.request_reset(f"user{number}@example.com").status_code, 202)
        self.assertEqual(self.request_reset("another@example.com").status_code, 429)

    def test_new_request_invalidates_the_previous_link(self):
        self.signup()
        self.request_reset()
        old_token = self.mailer.last_token()
        self.request_reset()
        new_token = self.mailer.last_token()
        self.assertNotEqual(old_token, new_token)
        old = self.client.post(RESET_CONFIRM_API, json={"token": old_token, "new_password": NEW_PASSWORD})
        self.assertEqual(old.status_code, 400)
        new = self.client.post(RESET_CONFIRM_API, json={"token": new_token, "new_password": NEW_PASSWORD})
        self.assertEqual(new.status_code, 200)

    def test_mail_failure_does_not_change_the_response(self):
        self.signup()
        failing_client = self.make_client(mailer=FailingMailer())
        with self.assertLogs("web.services.account_service", level="ERROR"):
            response = failing_client.post(RESET_REQUEST_API, json={"email": EMAIL})
        self.assertEqual(response.status_code, 202)

    def test_demo_environment_accepts_the_request_without_sending(self):
        client = self.make_client(app_env="demo")
        self.assertEqual(client.post(RESET_REQUEST_API, json={"email": EMAIL}).status_code, 202)


class ResetConfirmTest(AuthTestCase):
    def reset_token(self, email=EMAIL):
        self.client.post(RESET_REQUEST_API, json={"email": email})
        return self.mailer.last_token()

    def confirm(self, token, password=NEW_PASSWORD):
        return self.client.post(RESET_CONFIRM_API, json={"token": token, "new_password": password})

    def test_reset_changes_the_password(self):
        self.signup()
        response = self.confirm(self.reset_token())
        self.assertEqual(response.status_code, 200, response.text)
        other = self.make_auth_client()
        self.assertEqual(self.login(password=TEST_PASSWORD, client=other).status_code, 401)
        self.assertEqual(self.login(password=NEW_PASSWORD, client=other).status_code, 200)

    def test_reset_ends_every_session(self):
        self.signup_and_login()
        second = self.make_auth_client()
        self.assertEqual(self.login(client=second).status_code, 200)
        self.confirm(self.reset_token())
        for client in (self.client, second):
            self.assertIsNone(client.get(SESSION_API).json()["user"])
        with self.db() as db:
            self.assertEqual(db.scalars(select(AuthSession)).all(), [])

    def test_link_works_only_once(self):
        self.signup()
        token = self.reset_token()
        self.assertEqual(self.confirm(token).status_code, 200)
        again = self.confirm(token)
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["error"]["code"], "TOKEN_INVALID")

    def test_expired_link_is_rejected(self):
        self.signup()
        token = self.reset_token()
        with self.db() as db:
            row = db.scalar(select(AuthToken).where(AuthToken.purpose == "reset_password"))
            row.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.confirm(token).json()["error"]["code"], "TOKEN_INVALID")

    def test_verification_token_cannot_reset_a_password(self):
        self.signup()
        verification_token = self.mailer.last_token()
        response = self.confirm(verification_token)
        self.assertEqual(response.status_code, 400)

    def test_weak_password_is_rejected_and_the_link_stays_usable(self):
        self.signup()
        token = self.reset_token()
        weak = self.confirm(token, "short")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.json()["error"]["fields"])
        self.assertEqual(self.confirm(token).status_code, 200)

    def test_password_containing_the_email_is_rejected(self):
        self.signup()
        response = self.confirm(self.reset_token(), f"xx {EMAIL} xx")
        self.assertEqual(response.status_code, 400)

    def test_reset_marks_the_email_as_verified(self):
        self.signup()
        self.confirm(self.reset_token())
        with self.db() as db:
            self.assertIsNotNone(db.scalar(select(User)).email_verified_at)

    def test_reset_unlocks_a_locked_account(self):
        self.signup()
        for _ in range(5):
            self.login(password="wrong password here")
        self.assertEqual(self.login().status_code, 429)
        self.confirm(self.reset_token())
        self.assertEqual(self.login(password=NEW_PASSWORD).status_code, 200)

    def test_missing_or_oversized_input_is_rejected(self):
        self.assertEqual(self.client.post(RESET_CONFIRM_API, json={"token": "", "new_password": "x"}).status_code, 400)
        long_password = "a" * 1001
        self.assertEqual(self.confirm("token", long_password).status_code, 400)


class ChangePasswordTest(AuthTestCase):
    def change(self, headers, current=TEST_PASSWORD, new=NEW_PASSWORD, client=None):
        return (client or self.client).post(
            PASSWORD_API, json={"current_password": current, "new_password": new}, headers=headers
        )

    def test_change_keeps_this_session_and_ends_the_others(self):
        headers = self.verified_member()
        second = self.make_auth_client()
        self.assertEqual(self.login(client=second).status_code, 200)
        response = self.change(headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(SESSION_API).json()["user"]["email"], EMAIL)
        self.assertIsNone(second.get(SESSION_API).json()["user"])
        third = self.make_auth_client()
        self.assertEqual(self.login(password=TEST_PASSWORD, client=third).status_code, 401)
        self.assertEqual(self.login(password=NEW_PASSWORD, client=third).status_code, 200)

    def test_wrong_current_password_changes_nothing(self):
        headers = self.verified_member()
        response = self.change(headers, current="not my password")
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.json()["error"]["fields"])
        self.assertEqual(self.login(password=TEST_PASSWORD, client=self.make_auth_client()).status_code, 200)

    def test_five_wrong_attempts_lock_the_check_even_for_the_right_password(self):
        headers = self.verified_member()
        for _ in range(5):
            self.assertEqual(self.change(headers, current="not my password").status_code, 400)
        blocked = self.change(headers)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("retry-after", blocked.headers)

    def test_a_correct_password_resets_the_wrong_attempt_count(self):
        headers = self.verified_member()
        for _ in range(4):
            self.change(headers, current="not my password")
        self.assertEqual(self.change(headers).status_code, 200)
        with self.db() as db:
            checks = db.scalars(select(LoginAttempt).where(LoginAttempt.action == "password_check")).all()
            self.assertEqual(checks, [])

    def test_same_or_weak_new_password_is_rejected(self):
        headers = self.verified_member()
        same = self.change(headers, new=TEST_PASSWORD)
        self.assertEqual(same.status_code, 400)
        self.assertIn("new_password", same.json()["error"]["fields"])
        weak = self.change(headers, new="short")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.json()["error"]["fields"])

    def test_unverified_member_can_change_the_password(self):
        csrf_token = self.signup_and_login()
        response = self.change({"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 200)

    def test_requires_login_and_csrf_token(self):
        self.assertEqual(self.change({}).status_code, 401)
        self.signup_and_login()
        self.assertEqual(self.change({}).status_code, 403)


class MeTest(AuthTestCase):
    def test_me_returns_the_summary_without_secrets(self):
        self.verified_member()
        body = self.client.get(ME_API).json()
        self.assertEqual(
            body,
            {
                "email": EMAIL,
                "display_name": "학습자",
                "email_verified": True,
                "has_password": True,
                "social": [],
                "social_available": [],
            },
        )
        self.assertEqual(self.client.get(ME_API).headers["cache-control"], "no-store")

    def test_me_requires_login(self):
        self.assertEqual(self.client.get(ME_API).status_code, 401)

    def test_display_name_is_changed_and_trimmed(self):
        headers = self.verified_member()
        response = self.client.patch(ME_API, json={"display_name": "  새 이름  "}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["display_name"], "새 이름")
        self.assertEqual(self.client.get(ME_API).json()["display_name"], "새 이름")

    def test_invalid_display_names_are_rejected(self):
        headers = self.verified_member()
        for name in ("   ", "a" * 101, "bad\u0007name"):
            response = self.client.patch(ME_API, json={"display_name": name}, headers=headers)
            self.assertEqual(response.status_code, 400, name)
            self.assertIn("display_name", response.json()["error"]["fields"])

    def test_display_name_change_needs_a_verified_email(self):
        csrf_token = self.signup_and_login()
        response = self.client.patch(
            ME_API, json={"display_name": "이름"}, headers={"X-CSRF-Token": csrf_token}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "EMAIL_NOT_VERIFIED")


class LogoutAllTest(AuthTestCase):
    def test_every_session_including_this_one_ends(self):
        headers = self.verified_member()
        second = self.make_auth_client()
        self.assertEqual(self.login(client=second).status_code, 200)
        response = self.client.post(LOGOUT_ALL_API, headers=headers)
        self.assertEqual(response.status_code, 204)
        self.assertIn("sv_session=", response.headers["set-cookie"])
        for client in (self.client, second):
            self.assertIsNone(client.get(SESSION_API).json()["user"])

    def test_other_members_sessions_stay(self):
        headers = self.verified_member()
        other = self.make_auth_client()
        self.signup_and_login("other@example.com", client=other)
        self.client.post(LOGOUT_ALL_API, headers=headers)
        self.assertEqual(other.get(SESSION_API).json()["user"]["email"], "other@example.com")

    def test_requires_login_and_csrf_token(self):
        self.assertEqual(self.client.post(LOGOUT_ALL_API).status_code, 401)
        self.signup_and_login()
        self.assertEqual(self.client.post(LOGOUT_ALL_API).status_code, 403)


class DeleteAccountTest(AuthTestCase):
    def delete(self, headers, password=TEST_PASSWORD, client=None):
        return (client or self.client).post(DELETE_API, json={"password": password}, headers=headers)

    def test_wrong_password_keeps_the_account(self):
        headers = self.verified_member()
        response = self.delete(headers, "not my password")
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.json()["error"]["fields"])
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(User)).all()), 1)

    def test_deletion_removes_the_member_and_every_row_of_theirs(self):
        headers = self.verified_member()
        self.insert_words({"apple": "사과", "run": "달리다"})
        response = self.delete(headers)
        self.assertEqual(response.status_code, 204)
        self.assertIn("sv_session=", response.headers["set-cookie"])
        self.assertIsNone(self.client.get(SESSION_API).json()["user"])
        with self.db() as db:
            self.assertEqual(db.scalars(select(User)).all(), [])
            self.assertEqual(db.scalars(select(Word)).all(), [])
            self.assertEqual(db.scalars(select(AuthSession)).all(), [])

    def test_other_members_are_untouched(self):
        other = self.make_auth_client()
        self.verified_member("other@example.com", client=other)
        self.insert_words({"keep": "남김"}, email="other@example.com")
        headers = self.verified_member()
        self.delete(headers)
        with self.db() as db:
            self.assertEqual([user.email for user in db.scalars(select(User))], ["other@example.com"])
            self.assertEqual(len(db.scalars(select(Word)).all()), 1)

    def test_the_same_email_can_join_again(self):
        headers = self.verified_member()
        self.delete(headers)
        again = self.make_auth_client(ip="10.0.0.9")
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(minutes=2)
            db.commit()
        self.signup(client=again)
        self.assertEqual(self.login(client=again).status_code, 200)

    def test_unverified_member_can_leave(self):
        csrf_token = self.signup_and_login()
        self.assertEqual(self.delete({"X-CSRF-Token": csrf_token}).status_code, 204)

    def test_wrong_passwords_are_counted_and_limited(self):
        headers = self.verified_member()
        for _ in range(5):
            self.assertEqual(self.delete(headers, "not my password").status_code, 400)
        self.assertEqual(self.delete(headers).status_code, 429)

    def test_requires_login_and_csrf_token(self):
        self.assertEqual(self.delete({}).status_code, 401)
        self.signup_and_login()
        self.assertEqual(self.delete({}).status_code, 403)

    def test_delete_verb_on_me_is_not_offered(self):
        headers = self.verified_member()
        self.assertEqual(self.client.delete(ME_API, headers=headers).status_code, 405)


class AccountPagesTest(AuthTestCase):
    def test_account_page_redirects_to_login_when_signed_out(self):
        response = self.client.get("/account", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?next=%2Faccount")

    def test_account_page_shows_the_forms_and_the_menu_entry(self):
        self.verified_member()
        html = self.client.get("/account").text
        for element in ("name-form", "password-form", "logout-all-button", "delete-form", EMAIL):
            self.assertIn(element, html)
        self.assertIn('href="/account" aria-current="page"', html)
        self.assertIn("/static/account.js", html)
        self.assertNotIn("<script>", html)

    def test_account_page_escapes_the_display_name(self):
        self.signup_and_login()
        csrf_token = self.client.get(SESSION_API).json()["csrf_token"]
        self.verify_last_mail()
        payload = '"><script>alert(1)</script>'
        self.client.patch(ME_API, json={"display_name": payload}, headers={"X-CSRF-Token": csrf_token})
        html = self.client.get("/account").text
        self.assertNotIn("<script>alert(1)", html)

    def test_forgot_password_page(self):
        html = self.client.get("/forgot-password").text
        self.assertIn("forgot-form", html)
        self.assertNotIn("demo-reset-note", html)

    def test_forgot_password_page_explains_that_demo_sends_no_mail(self):
        html = self.make_client(app_env="demo").get("/forgot-password").text
        self.assertIn("demo-reset-note", html)

    def test_signed_in_member_is_sent_to_the_account_page(self):
        self.signup_and_login()
        response = self.client.get("/forgot-password", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account")

    def test_reset_password_page_has_the_form_and_no_inline_script(self):
        html = self.client.get("/reset-password").text
        self.assertIn("reset-form", html)
        self.assertNotIn("<script>", html)

    def test_login_page_links_to_the_reset_request_and_shows_the_withdrawn_notice(self):
        self.assertIn("/forgot-password", self.client.get("/login").text)
        self.assertNotIn("withdrawn-notice", self.client.get("/login").text)
        self.assertIn("withdrawn-notice", self.client.get("/login?withdrawn=1").text)


if __name__ == "__main__":
    unittest.main()

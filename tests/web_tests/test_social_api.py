#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 소셜 로그인 API와 화면 테스트 (FR-AUTH-15~17). 제공자는 가짜로 대신한다
# 파일 위치: tests/web_tests/test_social_api.py

import unittest
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from web_tests.support import SESSION_API, TEST_PASSWORD, AuthTestCase

from sqlalchemy import select

from web.db.base import utc_now
from web.db.tables import AuthSession, LoginAttempt, SocialAccount, User, UserSetting
from web.security.tokens import hash_token
from web.services.social_providers import ProviderProfile, SocialAuthError, pkce_challenge

API = "/api/v1/auth/social"
ME_API = "/api/v1/me"
PASSWORD_API = "/api/v1/me/password"
DELETE_API = "/api/v1/me/delete"
VERIFY_API = "/api/v1/auth/verify-email"
EMAIL = "learner@example.com"
SOCIAL_EMAIL = "social@example.com"
NEW_PASSWORD = "another long passphrase 42"


class FakeProvider:
    """실제 제공자 대신 정해 둔 사용자 정보를 돌려주는 제공자."""

    def __init__(self, name, profile=None, error=False):
        self.name = name
        self.profile = profile
        self.error = error
        self.calls = []

    def authorize_url(self, redirect_uri, state, code_challenge):
        return (
            f"https://{self.name}.provider.test/authorize?state={state}"
            f"&code_challenge={code_challenge}&redirect_uri={redirect_uri}"
        )

    def fetch_profile(self, redirect_uri, code, code_verifier):
        self.calls.append((redirect_uri, code, code_verifier))
        if self.error:
            raise SocialAuthError("실패")
        return self.profile


def profile(subject="g-1", email=SOCIAL_EMAIL, verified=True, name="소셜이름"):
    return ProviderProfile(subject, email, verified, name)


class SocialTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.google = FakeProvider("google", profile())
        self.kakao = FakeProvider("kakao", profile("k-1"))
        self.providers = {"google": self.google, "kakao": self.kakao}
        self.client = self.make_social_client()

    def make_social_client(self, ip="testclient"):
        return self.make_client(mailer=self.mailer, ip=ip, social_providers=self.providers)

    def begin(self, provider="google", client=None):
        """시작 요청을 보내고 제공자에게 보낸 state를 돌려준다."""
        response = (client or self.client).get(f"{API}/{provider}/start", follow_redirects=False)
        self.assertEqual(response.status_code, 302, response.text)
        return parse_qs(urlparse(response.headers["location"]).query)["state"][0]

    def callback(self, state, provider="google", client=None, **query):
        params = {"code": "auth-code", "state": state, **query}
        return (client or self.client).get(
            f"{API}/{provider}/callback", params=params, follow_redirects=False
        )

    def social_login(self, provider="google", client=None):
        return self.callback(self.begin(provider, client), provider, client)

    def users(self):
        with self.db() as db:
            return db.scalars(select(User).order_by(User.id)).all()

    def accounts(self):
        with self.db() as db:
            return [(a.provider, a.provider_user_id, a.user_id) for a in db.scalars(select(SocialAccount))]

    def pending_rows(self):
        with self.db() as db:
            return db.scalars(select(AuthSession).where(AuthSession.user_id.is_(None))).all()

    def current_email(self, client=None):
        user = (client or self.client).get(SESSION_API).json()["user"]
        return user and user["email"]


class StartTest(SocialTestCase):
    def test_start_redirects_to_the_provider_with_state_and_pkce(self):
        response = self.client.get(f"{API}/google/start", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response.headers["location"]).query)
        self.assertEqual(
            query["redirect_uri"], ["https://voca.example.test/api/v1/auth/social/google/callback"]
        )
        row = self.pending_rows()[0]
        self.assertEqual(query["state"], [row.oauth_state])
        self.assertEqual(query["code_challenge"], [pkce_challenge(row.oauth_code_verifier)])
        self.assertGreaterEqual(len(row.oauth_code_verifier), 43)
        self.assertLessEqual(len(row.oauth_code_verifier), 128)

    def test_start_sets_only_the_oauth_cookie_and_it_is_http_only(self):
        response = self.client.get(f"{API}/google/start", follow_redirects=False)
        cookie_header = response.headers["set-cookie"]
        self.assertIn("sv_oauth=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertNotIn("sv_session", cookie_header)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_each_start_has_its_own_state(self):
        self.assertNotEqual(self.begin(), self.begin())

    def test_unconfigured_or_unknown_provider_is_not_found(self):
        client = self.make_client(social_providers={"google": self.google})
        self.assertEqual(client.get(f"{API}/kakao/start", follow_redirects=False).status_code, 404)
        self.assertEqual(self.client.get(f"{API}/naver/start", follow_redirects=False).status_code, 404)

    def test_starts_are_limited_per_ip(self):
        for _ in range(30):
            self.assertEqual(self.client.get(f"{API}/google/start", follow_redirects=False).status_code, 302)
        blocked = self.client.get(f"{API}/google/start", follow_redirects=False)
        self.assertEqual(blocked.status_code, 429)

    def test_expired_start_rows_are_cleaned_up(self):
        self.begin()
        with self.db() as db:
            row = db.scalar(select(AuthSession))
            row.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.begin()
        self.assertEqual(len(self.pending_rows()), 1)


class CallbackAccountRulesTest(SocialTestCase):
    def test_new_member_with_verified_email_is_created_and_logged_in(self):
        response = self.social_login()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        self.assertIn("sv_session=", response.headers["set-cookie"])
        (user,) = self.users()
        self.assertEqual(user.email, SOCIAL_EMAIL)
        self.assertIsNone(user.password_hash)
        self.assertIsNotNone(user.email_verified_at)
        self.assertIsNotNone(user.terms_agreed_at)
        self.assertEqual(user.display_name, "소셜이름")
        self.assertEqual(self.accounts(), [("google", "g-1", user.id)])
        with self.db() as db:
            self.assertIsNotNone(db.get(UserSetting, user.id))
        self.assertEqual(self.current_email(), SOCIAL_EMAIL)
        self.assertEqual(self.pending_rows(), [])

    def test_the_provider_is_called_with_the_code_and_the_stored_verifier(self):
        self.begin()
        row = self.pending_rows()[0]
        state, verifier = row.oauth_state, row.oauth_code_verifier
        self.callback(state)
        redirect_uri, code, used_verifier = self.google.calls[0]
        self.assertEqual(code, "auth-code")
        self.assertEqual(used_verifier, verifier)
        self.assertEqual(redirect_uri, "https://voca.example.test/api/v1/auth/social/google/callback")

    def test_linked_social_account_logs_in_the_same_member(self):
        self.social_login()
        self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": self.client.get(SESSION_API).json()["csrf_token"]})
        other = self.make_social_client(ip="10.0.0.5")
        self.social_login(client=other)
        self.assertEqual(len(self.users()), 1)
        self.assertEqual(self.current_email(other), SOCIAL_EMAIL)

    def test_verified_email_of_an_existing_member_is_linked_and_the_password_is_kept(self):
        self.signup(SOCIAL_EMAIL)
        self.verify_last_mail()
        self.social_login()
        (user,) = self.users()
        self.assertIsNotNone(user.password_hash)
        self.assertEqual(self.accounts(), [("google", "g-1", user.id)])
        self.assertEqual(self.current_email(), SOCIAL_EMAIL)
        other = self.make_auth_client(ip="10.0.0.6")
        self.assertEqual(self.login(SOCIAL_EMAIL, client=other).status_code, 200)

    def test_squatted_unverified_account_loses_its_password_when_the_real_owner_arrives(self):
        self.signup(SOCIAL_EMAIL)  # 남의 이메일로 먼저 가입해 둔 공격자
        attacker = self.make_auth_client(ip="10.0.0.7")
        self.assertEqual(self.login(SOCIAL_EMAIL, client=attacker).status_code, 200)
        self.social_login()
        (user,) = self.users()
        self.assertIsNone(user.password_hash)
        self.assertIsNotNone(user.email_verified_at)
        self.assertIsNone(attacker.get(SESSION_API).json()["user"])
        self.assertEqual(self.login(SOCIAL_EMAIL, client=self.make_auth_client(ip="10.0.0.8")).status_code, 401)
        self.assertEqual(self.current_email(), SOCIAL_EMAIL)

    def test_unverified_provider_email_waits_for_the_email_step(self):
        self.google.profile = profile(verified=False)
        response = self.social_login()
        self.assertEqual(response.headers["location"], "/signup/social")
        self.assertNotIn("sv_session=", response.headers.get("set-cookie", ""))
        # 이메일 입력 단계에서 쓸 대기 쿠키는 지우지 않는다
        self.assertNotIn("Max-Age=0", response.headers.get("set-cookie", ""))
        self.assertIn("sv_oauth", self.client.cookies)
        self.assertEqual(self.users(), [])
        (row,) = self.pending_rows()
        self.assertEqual(row.pending_provider_user_id, "g-1")
        self.assertIsNone(row.oauth_state)

    def test_missing_email_waits_for_the_email_step(self):
        self.google.profile = profile(email=None, verified=False)
        self.assertEqual(self.social_login().headers["location"], "/signup/social")
        self.assertEqual(self.users(), [])

    def test_unverified_provider_email_never_links_to_an_existing_member(self):
        self.signup(SOCIAL_EMAIL)
        self.google.profile = profile(verified=False)
        response = self.social_login()
        self.assertEqual(response.headers["location"], "/signup/social")
        self.assertEqual(self.accounts(), [])
        self.assertIsNone(self.current_email())

    def test_display_name_falls_back_to_the_email_name_then_a_default(self):
        self.google.profile = profile(name=None)
        self.social_login()
        self.assertEqual(self.users()[0].display_name, "social")
        self.kakao.profile = profile("k-2", email=None, verified=False, name=None)
        self.kakao.profile = profile("k-2", email="x@example.com", name="a" * 300)
        self.social_login("kakao", client=self.make_social_client(ip="10.0.0.9"))
        self.assertEqual(len(self.users()[1].display_name), 100)

    def test_social_login_replaces_an_earlier_session_of_the_browser(self):
        self.signup()
        self.login()
        old_hash = hash_token(self.client.cookies.get("sv_session"))
        self.social_login()
        with self.db() as db:
            self.assertIsNone(db.scalar(select(AuthSession).where(AuthSession.token_hash == old_hash)))
        self.assertEqual(self.current_email(), SOCIAL_EMAIL)


class CallbackProtectionTest(SocialTestCase):
    def assert_state_error(self, response):
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?social_error=state")
        self.assertNotIn("sv_session=", response.headers.get("set-cookie", ""))
        self.assertEqual(self.users(), [])

    def test_wrong_state_is_rejected_and_burns_the_attempt(self):
        state = self.begin()
        self.assert_state_error(self.callback("not-the-state"))
        self.assert_state_error(self.callback(state))

    def test_the_same_callback_cannot_be_used_twice(self):
        state = self.begin()
        self.assertEqual(self.callback(state).headers["location"], "/")
        other = self.make_social_client(ip="10.0.0.5")
        self.assertEqual(self.callback(state, client=other).headers["location"], "/login?social_error=state")
        self.assertEqual(len(self.google.calls), 1)

    def test_callback_without_the_oauth_cookie_is_rejected(self):
        state = self.begin()
        self.client.cookies.clear()
        self.assert_state_error(self.callback(state))
        self.assertEqual(self.google.calls, [])

    def test_state_of_another_browser_is_rejected(self):
        other = self.make_social_client(ip="10.0.0.5")
        other_state = self.begin(client=other)
        self.begin()
        self.assert_state_error(self.callback(other_state))
        self.assertEqual(self.google.calls, [])

    def test_expired_start_is_rejected(self):
        state = self.begin()
        with self.db() as db:
            row = db.scalar(select(AuthSession))
            row.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assert_state_error(self.callback(state))
        self.assertEqual(self.google.calls, [])

    def test_state_of_another_provider_is_rejected(self):
        state = self.begin("google")
        self.assert_state_error(self.callback(state, provider="kakao"))

    def test_missing_state_is_rejected(self):
        self.begin()
        response = self.client.get(f"{API}/google/callback", params={"code": "x"}, follow_redirects=False)
        self.assert_state_error(response)

    def test_provider_denial_is_reported_and_clears_the_attempt(self):
        state = self.begin()
        response = self.client.get(
            f"{API}/google/callback",
            params={"error": "access_denied", "state": state},
            follow_redirects=False,
        )
        self.assertEqual(response.headers["location"], "/login?social_error=denied")
        self.assertEqual(self.pending_rows(), [])
        self.assertEqual(self.google.calls, [])

    def test_failed_exchange_is_reported_without_creating_anything(self):
        self.google.error = True
        response = self.social_login()
        self.assertEqual(response.headers["location"], "/login?social_error=provider")
        self.assertEqual(self.users(), [])
        self.assertEqual(self.pending_rows(), [])

    def test_unconfigured_provider_callback_goes_back_to_login(self):
        client = self.make_client(social_providers={})
        response = client.get(f"{API}/google/callback", params={"code": "x", "state": "y"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?social_error=unavailable")


class SignupWithoutEmailTest(SocialTestCase):
    def reach_email_step(self, **profile_overrides):
        self.google.profile = profile(email=None, verified=False, **profile_overrides)
        self.assertEqual(self.social_login().headers["location"], "/signup/social")

    def complete(self, email="new@example.com", client=None):
        return (client or self.client).post(f"{API}/complete", json={"email": email})

    def test_email_step_page_needs_a_pending_signup(self):
        self.assertEqual(self.client.get("/signup/social", follow_redirects=False).status_code, 303)
        self.reach_email_step()
        html = self.client.get("/signup/social").text
        self.assertIn("social-complete-form", html)
        self.assertNotIn("<script>", html)

    def test_entering_an_email_sends_a_verification_mail(self):
        self.reach_email_step()
        response = self.complete()
        self.assertEqual(response.status_code, 202)
        message = self.mailer.messages[-1]
        self.assertEqual(message.recipient, "new@example.com")
        self.assertIn("/verify-email#token=", message.body)
        self.assertEqual(self.users(), [])

    def test_following_the_link_creates_the_member_and_links_the_social_account(self):
        self.reach_email_step(name="이름")
        self.complete()
        token = self.mailer.last_token()
        response = self.client.post(VERIFY_API, json={"token": token})
        self.assertEqual(response.status_code, 200)
        self.assertIn("가입이 완료", response.json()["message"])
        (user,) = self.users()
        self.assertEqual(user.email, "new@example.com")
        self.assertIsNone(user.password_hash)
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(user.display_name, "이름")
        self.assertEqual(self.accounts(), [("google", "g-1", user.id)])
        self.assertEqual(self.pending_rows(), [])
        # 인증 링크로는 로그인되지 않고, 소셜 로그인으로 들어온다
        self.assertIsNone(self.current_email())
        self.google.profile = profile(email=None, verified=False)
        self.social_login()
        self.assertEqual(self.current_email(), "new@example.com")

    def test_the_link_works_only_once(self):
        self.reach_email_step()
        self.complete()
        token = self.mailer.last_token()
        self.assertEqual(self.client.post(VERIFY_API, json={"token": token}).status_code, 200)
        again = self.client.post(VERIFY_API, json={"token": token})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["error"]["code"], "TOKEN_INVALID")
        self.assertEqual(len(self.users()), 1)

    def test_expired_link_is_rejected(self):
        self.reach_email_step()
        self.complete()
        token = self.mailer.last_token()
        with self.db() as db:
            row = db.scalar(select(AuthSession).where(AuthSession.user_id.is_(None)))
            row.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.post(VERIFY_API, json={"token": token}).status_code, 400)
        self.assertEqual(self.users(), [])

    def test_an_already_registered_email_gets_a_notice_and_the_same_response(self):
        self.signup("taken@example.com")
        self.reach_email_step()
        fresh = self.complete("new@example.com")
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(minutes=2)
            db.commit()
        taken = self.complete("taken@example.com")
        self.assertEqual(fresh.json(), taken.json())
        self.assertIn("이미 가입", self.mailer.messages[-1].subject)
        self.assertNotIn("#token=", self.mailer.messages[-1].body)

    def test_registration_between_mail_and_link_blocks_the_link(self):
        self.reach_email_step()
        self.complete("new@example.com")
        token = self.mailer.last_token()
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(minutes=2)
            db.commit()
        self.signup("new@example.com", client=self.make_auth_client(ip="10.0.0.5"))
        response = self.client.post(VERIFY_API, json={"token": token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.accounts(), [])

    def test_email_step_without_a_pending_signup_is_rejected(self):
        response = self.complete()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "SIGNUP_EXPIRED")

    def test_malformed_email_is_rejected(self):
        self.reach_email_step()
        response = self.complete("not-an-email")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["error"]["fields"])

    def test_the_same_address_is_limited_to_one_mail_a_minute(self):
        self.reach_email_step()
        self.assertEqual(self.complete().status_code, 202)
        self.assertEqual(self.complete().status_code, 429)

    def test_an_ordinary_verification_token_does_not_complete_a_social_signup(self):
        self.signup()
        token = self.mailer.last_token()
        self.assertEqual(self.client.post(VERIFY_API, json={"token": token}).status_code, 200)
        self.assertEqual(len(self.users()), 1)


class LinkAndUnlinkTest(SocialTestCase):
    def link(self, headers, provider="google", password=TEST_PASSWORD, client=None):
        return (client or self.client).post(f"{API}/{provider}/link", json={"password": password}, headers=headers)

    def finish_link(self, response, provider="google", client=None):
        state = parse_qs(urlparse(response.json()["authorize_url"]).query)["state"][0]
        return self.callback(state, provider, client)

    def test_link_needs_login_and_csrf(self):
        self.assertEqual(self.link({}).status_code, 401)
        self.signup_and_login()
        self.assertEqual(self.link({}).status_code, 403)

    def test_wrong_password_starts_nothing(self):
        headers = self.verified_member()
        response = self.link(headers, password="not my password")
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.json()["error"]["fields"])
        self.assertEqual(self.pending_rows(), [])

    def test_linking_keeps_the_current_login_and_adds_the_account(self):
        headers = self.verified_member()
        start = self.link(headers)
        self.assertEqual(start.status_code, 200)
        self.assertIn("sv_oauth=", start.headers["set-cookie"])
        done = self.finish_link(start)
        self.assertEqual(done.headers["location"], "/account?social=linked")
        self.assertNotIn("sv_session=", done.headers["set-cookie"])
        self.assertEqual(self.current_email(), EMAIL)
        self.assertEqual(self.client.get(ME_API).json()["social"], ["google"])
        self.assertEqual(len(self.users()), 1)

    def test_social_account_of_another_member_cannot_be_taken(self):
        self.social_login()  # google g-1은 소셜 회원의 것
        other = self.make_social_client(ip="10.0.0.5")
        headers = self.verified_member("mine@example.com", client=other)
        done = self.finish_link(self.link(headers, client=other), client=other)
        self.assertEqual(done.headers["location"], "/account?social_error=taken")
        self.assertEqual(len(self.accounts()), 1)

    def test_a_second_account_of_the_same_provider_is_refused(self):
        headers = self.verified_member()
        self.finish_link(self.link(headers))
        self.google.profile = profile("g-2", email="x@example.com")
        done = self.finish_link(self.link(headers))
        self.assertEqual(done.headers["location"], "/account?social_error=taken")
        self.assertEqual(len(self.accounts()), 1)

    def test_linking_again_the_same_account_is_harmless(self):
        headers = self.verified_member()
        self.finish_link(self.link(headers))
        done = self.finish_link(self.link(headers))
        self.assertEqual(done.headers["location"], "/account?social=linked")
        self.assertEqual(len(self.accounts()), 1)

    def test_link_error_goes_back_to_the_account_page(self):
        headers = self.verified_member()
        self.google.error = True
        done = self.finish_link(self.link(headers))
        self.assertEqual(done.headers["location"], "/account?social_error=provider")
        self.assertEqual(self.accounts(), [])

    def test_unlink_removes_the_connection(self):
        headers = self.verified_member()
        self.finish_link(self.link(headers))
        response = self.client.delete(f"{API}/google", headers=headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.accounts(), [])
        self.assertEqual(self.client.delete(f"{API}/google", headers=headers).status_code, 204)

    def test_unlink_needs_a_verified_member(self):
        csrf_token = self.signup_and_login()
        response = self.client.delete(f"{API}/google", headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(response.status_code, 403)

    def test_unknown_provider_cannot_be_unlinked(self):
        headers = self.verified_member()
        self.assertEqual(self.client.delete(f"{API}/naver", headers=headers).status_code, 404)

    def test_last_login_method_cannot_be_removed(self):
        self.social_login()
        headers = {"X-CSRF-Token": self.client.get(SESSION_API).json()["csrf_token"]}
        response = self.client.delete(f"{API}/google", headers=headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "LAST_LOGIN_METHOD")
        self.assertEqual(len(self.accounts()), 1)

    def test_a_second_connection_lets_the_first_be_removed(self):
        self.social_login()
        headers = {"X-CSRF-Token": self.client.get(SESSION_API).json()["csrf_token"]}
        self.finish_link(self.link(headers, "kakao", password=""), "kakao")
        self.assertEqual(self.client.delete(f"{API}/google", headers=headers).status_code, 204)
        self.assertEqual([a[0] for a in self.accounts()], ["kakao"])

    def test_unlink_is_allowed_when_a_password_exists(self):
        headers = self.verified_member()
        self.finish_link(self.link(headers))
        self.assertEqual(self.client.delete(f"{API}/google", headers=headers).status_code, 204)


class SocialOnlyAccountTest(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.social_login()
        self.headers = {"X-CSRF-Token": self.client.get(SESSION_API).json()["csrf_token"]}

    def test_me_reports_no_password_and_the_connections(self):
        body = self.client.get(ME_API).json()
        self.assertFalse(body["has_password"])
        self.assertEqual(body["social"], ["google"])
        self.assertEqual(body["social_available"], ["google", "kakao"])
        self.assertNotIn("g-1", str(body))

    def test_a_password_can_be_set_without_the_current_one(self):
        response = self.client.post(PASSWORD_API, json={"new_password": NEW_PASSWORD}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        other = self.make_auth_client(ip="10.0.0.5")
        self.assertEqual(self.login(SOCIAL_EMAIL, NEW_PASSWORD, other).status_code, 200)
        self.assertTrue(self.client.get(ME_API).json()["has_password"])

    def test_the_set_password_is_still_checked_for_strength(self):
        response = self.client.post(PASSWORD_API, json={"new_password": "short"}, headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_account_deletion_needs_a_password_first(self):
        response = self.client.post(DELETE_API, json={"password": ""}, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.json()["error"]["fields"])
        self.assertEqual(len(self.users()), 1)
        self.client.post(PASSWORD_API, json={"new_password": NEW_PASSWORD}, headers=self.headers)
        done = self.client.post(DELETE_API, json={"password": NEW_PASSWORD}, headers=self.headers)
        self.assertEqual(done.status_code, 204)
        self.assertEqual(self.users(), [])
        self.assertEqual(self.accounts(), [])

    def test_a_password_login_is_refused_until_one_is_set(self):
        other = self.make_auth_client(ip="10.0.0.5")
        self.assertEqual(self.login(SOCIAL_EMAIL, NEW_PASSWORD, other).status_code, 401)

    def test_the_reset_mail_lets_a_social_member_set_a_password(self):
        other = self.make_auth_client(ip="10.0.0.5")
        other.post("/api/v1/auth/password-reset/request", json={"email": SOCIAL_EMAIL})
        token = self.mailer.last_token()
        response = other.post(
            "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.login(SOCIAL_EMAIL, NEW_PASSWORD, other).status_code, 200)


class SocialPagesTest(SocialTestCase):
    def test_login_and_signup_pages_show_buttons_for_configured_providers(self):
        for path in ("/login", "/signup"):
            html = self.client.get(path).text
            self.assertIn("/api/v1/auth/social/google/start", html)
            self.assertIn("/api/v1/auth/social/kakao/start", html)
        only_google = self.make_client(social_providers={"google": self.google}).get("/login").text
        self.assertIn("social-google", only_google)
        self.assertNotIn("social-kakao", only_google)

    def test_no_buttons_without_providers(self):
        client = self.make_client(social_providers={})
        for path in ("/login", "/signup"):
            self.assertNotIn("social-login", client.get(path).text)

    def test_login_page_explains_known_error_codes_and_ignores_others(self):
        html = self.client.get("/login?social_error=denied").text
        self.assertIn("social-error", html)
        self.assertIn("취소", html)
        hostile = self.client.get("/login?social_error=%3Cscript%3Ealert(1)%3C/script%3E").text
        self.assertNotIn("alert(1)", hostile)
        self.assertNotIn("social-error", hostile)

    def test_account_page_shows_connections(self):
        headers = self.verified_member()
        self.client.post(f"{API}/google/link", json={"password": TEST_PASSWORD}, headers=headers)
        html = self.client.get("/account").text
        self.assertIn("social-section", html)
        self.assertIn("social-link", html)
        self.assertIn("social_password", html)
        self.assertNotIn("<script>", html)

    def test_account_page_of_a_social_only_member_has_no_current_password_field(self):
        self.social_login()
        html = self.client.get("/account").text
        self.assertIn("no-password-note", html)
        self.assertNotIn('id="current_password"', html)
        self.assertNotIn("social_password", html)
        self.assertIn("social-unlink", html)

    def test_account_page_without_providers_has_no_social_section(self):
        client = self.make_client(mailer=self.mailer, social_providers={})
        self.signup_and_login(client=client)
        self.assertNotIn("social-section", client.get("/account").text)

    def test_linked_notice_comes_from_the_query(self):
        self.verified_member()
        self.assertIn("social-linked-notice", self.client.get("/account?social=linked").text)


if __name__ == "__main__":
    unittest.main()

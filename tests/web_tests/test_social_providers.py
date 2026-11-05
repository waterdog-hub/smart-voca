#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 구글·카카오 어댑터를 모의 전송으로 확인한다. 실제 제공자는 호출하지 않는다 (이슈 #19)
# 파일 위치: tests/web_tests/test_social_providers.py

import unittest
from urllib.parse import parse_qs, urlparse

import httpx

from web_tests.support import WebTestCase

from web.services.social_providers import (
    GoogleProvider,
    KakaoProvider,
    SocialAuthError,
    create_social_providers,
    pkce_challenge,
)

REDIRECT = "https://voca.example.test/api/v1/auth/social/google/callback"


def make_transport(token_json=None, profile_json=None, token_status=200, profile_status=200, requests=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.path in ("/token", "/oauth/token"):
            return httpx.Response(token_status, json=token_json if token_json is not None else {"access_token": "tok"})
        return httpx.Response(profile_status, json=profile_json if profile_json is not None else {})

    return httpx.MockTransport(handler)


class PkceTest(unittest.TestCase):
    def test_s256_challenge_matches_the_rfc_7636_example(self):
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        self.assertEqual(pkce_challenge(verifier), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")


class AuthorizeUrlTest(unittest.TestCase):
    def test_google_url_carries_state_pkce_and_scopes(self):
        url = GoogleProvider("client-id", "secret").authorize_url(REDIRECT, "the-state", "the-challenge")
        parsed = urlparse(url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "accounts.google.com", "/o/oauth2/v2/auth"))
        query = parse_qs(parsed.query)
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], [REDIRECT])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["state"], ["the-state"])
        self.assertEqual(query["code_challenge"], ["the-challenge"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], ["openid email profile"])
        self.assertNotIn("secret", url)

    def test_kakao_url_asks_for_email_and_nickname(self):
        url = KakaoProvider("rest-key", None).authorize_url(REDIRECT, "s", "c")
        parsed = urlparse(url)
        self.assertEqual((parsed.netloc, parsed.path), ("kauth.kakao.com", "/oauth/authorize"))
        self.assertEqual(parse_qs(parsed.query)["scope"], ["account_email profile_nickname"])


class FetchProfileTest(unittest.TestCase):
    def test_google_exchange_sends_code_verifier_and_bearer_token(self):
        requests = []
        provider = GoogleProvider(
            "client-id",
            "secret",
            make_transport(
                profile_json={"sub": "123", "email": " Person@Example.com ", "email_verified": True, "name": "이름"},
                requests=requests,
            ),
        )
        result = provider.fetch_profile(REDIRECT, "the-code", "the-verifier")
        self.assertEqual(
            (result.provider_user_id, result.email, result.email_verified, result.display_name),
            ("123", "person@example.com", True, "이름"),
        )
        token_request, profile_request = requests
        self.assertEqual(token_request.method, "POST")
        form = parse_qs(token_request.content.decode())
        self.assertEqual(form["code"], ["the-code"])
        self.assertEqual(form["code_verifier"], ["the-verifier"])
        self.assertEqual(form["grant_type"], ["authorization_code"])
        self.assertEqual(form["client_secret"], ["secret"])
        self.assertEqual(form["redirect_uri"], [REDIRECT])
        self.assertEqual(profile_request.headers["authorization"], "Bearer tok")

    def test_google_email_counts_as_verified_only_when_the_flag_is_true(self):
        for flag in (False, "true", None, 1):
            provider = GoogleProvider(
                "c", "s", make_transport(profile_json={"sub": "1", "email": "a@example.com", "email_verified": flag})
            )
            self.assertFalse(provider.fetch_profile(REDIRECT, "c", "v").email_verified, flag)

    def test_google_without_email_is_never_verified(self):
        provider = GoogleProvider("c", "s", make_transport(profile_json={"sub": "1", "email_verified": True}))
        result = provider.fetch_profile(REDIRECT, "c", "v")
        self.assertIsNone(result.email)
        self.assertFalse(result.email_verified)

    def test_google_profile_without_subject_is_rejected(self):
        for body in ({"email": "a@example.com"}, {"sub": ""}, {"sub": 5}, {"sub": "x" * 256}, []):
            provider = GoogleProvider("c", "s", make_transport(profile_json=body))
            with self.assertRaises(SocialAuthError, msg=body):
                provider.fetch_profile(REDIRECT, "c", "v")

    def test_kakao_needs_both_valid_and_verified_flags(self):
        def kakao(account):
            body = {"id": 4242, "kakao_account": account}
            return KakaoProvider("key", "secret", make_transport(profile_json=body)).fetch_profile(REDIRECT, "c", "v")

        good = kakao({"email": "K@Example.com", "is_email_valid": True, "is_email_verified": True,
                      "profile": {"nickname": "닉"}})
        self.assertEqual((good.provider_user_id, good.email, good.email_verified, good.display_name),
                         ("4242", "k@example.com", True, "닉"))
        self.assertFalse(kakao({"email": "k@example.com", "is_email_valid": True, "is_email_verified": False}).email_verified)
        self.assertFalse(kakao({"email": "k@example.com", "is_email_valid": False, "is_email_verified": True}).email_verified)
        self.assertFalse(kakao({"email": "k@example.com"}).email_verified)

    def test_kakao_without_consent_has_no_email(self):
        provider = KakaoProvider("key", None, make_transport(profile_json={"id": 7}))
        result = provider.fetch_profile(REDIRECT, "c", "v")
        self.assertEqual((result.provider_user_id, result.email, result.email_verified), ("7", None, False))

    def test_kakao_sends_no_secret_when_none_is_configured(self):
        requests = []
        KakaoProvider("key", None, make_transport(profile_json={"id": 7}, requests=requests)).fetch_profile(
            REDIRECT, "c", "v"
        )
        self.assertNotIn("client_secret", parse_qs(requests[0].content.decode()))

    def test_kakao_member_number_must_be_an_integer(self):
        for body in ({"id": "7"}, {"id": True}, {"id": None}, {}):
            provider = KakaoProvider("key", None, make_transport(profile_json=body))
            with self.assertRaises(SocialAuthError, msg=body):
                provider.fetch_profile(REDIRECT, "c", "v")

    def test_provider_errors_become_social_auth_errors(self):
        cases = {
            "token rejected": make_transport(token_status=400),
            "no access token": make_transport(token_json={"error": "x"}),
            "profile rejected": make_transport(profile_status=401),
        }
        for name, transport in cases.items():
            with self.assertRaises(SocialAuthError, msg=name):
                GoogleProvider("c", "s", transport).fetch_profile(REDIRECT, "c", "v")

    def test_a_non_json_reply_becomes_a_social_auth_error(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html>proxy error</html>"))
        with self.assertRaises(SocialAuthError):
            GoogleProvider("c", "s", transport).fetch_profile(REDIRECT, "c", "v")

    def test_a_network_failure_becomes_a_social_auth_error(self):
        def refuse(request):
            raise httpx.ConnectError("연결 실패", request=request)

        with self.assertRaises(SocialAuthError):
            GoogleProvider("c", "s", httpx.MockTransport(refuse)).fetch_profile(REDIRECT, "c", "v")

    def test_the_error_does_not_carry_the_provider_reply(self):
        transport = make_transport(token_status=400, token_json={"error": "secret-detail-from-provider"})
        with self.assertRaises(SocialAuthError) as raised:
            GoogleProvider("c", "s", transport).fetch_profile(REDIRECT, "the-code", "v")
        self.assertNotIn("secret-detail", str(raised.exception))
        self.assertNotIn("the-code", str(raised.exception))


class CreateProvidersTest(WebTestCase):
    def settings_with(self, app_env="local", **keys):
        settings = self.make_settings(app_env)
        for name, value in keys.items():
            setattr(settings, name, value)
        return settings

    def test_nothing_is_enabled_without_keys(self):
        self.assertEqual(create_social_providers(self.settings_with()), {})

    def test_google_needs_both_id_and_secret(self):
        self.assertEqual(create_social_providers(self.settings_with(google_client_id="id")), {})
        providers = create_social_providers(self.settings_with(google_client_id="id", google_client_secret="s"))
        self.assertEqual(list(providers), ["google"])

    def test_kakao_needs_only_the_rest_api_key(self):
        providers = create_social_providers(self.settings_with(kakao_rest_api_key="key"))
        self.assertEqual(list(providers), ["kakao"])

    def test_the_demo_environment_never_enables_providers(self):
        settings = self.settings_with(
            "demo", google_client_id="id", google_client_secret="s", kakao_rest_api_key="key"
        )
        self.assertEqual(create_social_providers(settings), {})


if __name__ == "__main__":
    unittest.main()

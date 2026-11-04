#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 가입·로그인·인증 화면이 뜨고 핵심 요소가 보이는지 확인한다
# 파일 위치: tests/web_tests/test_auth_pages.py

import unittest

from web_tests.support import SIGNUP_API, AuthTestCase

PUBLIC_PAGES = ("/login", "/signup", "/signup/sent", "/verify-email")


class AuthPagesTest(AuthTestCase):
    def test_public_pages_open_without_inline_scripts(self):
        # M10의 CSP script-src 'self'와 충돌하지 않게 스크립트는 파일로만 둔다
        for path in PUBLIC_PAGES:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('lang="ko"', response.text)
                self.assertIn('src="/static/auth.js"', response.text)
                self.assertNotIn("<script>", response.text)
                self.assertNotIn("onclick=", response.text)
                self.assertNotIn("style=", response.text)

    def test_login_page_has_labeled_inputs(self):
        html = self.client.get("/login").text
        self.assertIn('<label for="email">', html)
        self.assertIn('<label for="password">', html)
        self.assertIn('autocomplete="current-password"', html)

    def test_signup_page_has_required_agreements(self):
        html = self.client.get("/signup").text
        self.assertIn('id="terms_agreed"', html)
        self.assertIn('id="privacy_agreed"', html)
        self.assertIn('autocomplete="new-password"', html)

    def test_verify_page_does_not_consume_token_by_itself(self):
        self.signup()
        self.client.get("/verify-email")
        self.verify_last_mail()

    def test_static_files_are_served(self):
        self.assertEqual(self.client.get("/static/auth.js").status_code, 200)
        self.assertEqual(self.client.get("/static/app.css").status_code, 200)

    def test_login_and_signup_redirect_home_when_logged_in(self):
        self.signup_and_login()
        for path in ("/login", "/signup"):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 303, path)
            self.assertEqual(response.headers["location"], "/")

    def test_home_shows_verification_banner_until_verified(self):
        self.signup_and_login()
        response = self.client.get("/")
        self.assertIn('id="resend-button"', response.text)
        self.assertIn("학습자", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.verify_last_mail()
        self.assertNotIn('id="resend-button"', self.client.get("/").text)

    def test_display_name_is_escaped(self):
        payload = self.signup_payload(display_name="<script>alert(1)</script>")
        self.assertEqual(self.client.post(SIGNUP_API, json=payload).status_code, 202)
        self.login()
        html = self.client.get("/").text
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_words_page_requires_login(self):
        response = self.client.get("/words", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?next=%2Fwords")

    def test_words_page_has_core_elements_without_inline_code(self):
        self.verified_member()
        response = self.client.get("/words")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        html = response.text
        for element in ('id="word-search"', 'id="add-form"', 'id="import-file"', 'id="edit-panel"',
                        'id="delete-selected"', 'href="/api/v1/words/export"', 'aria-current="page"'):
            self.assertIn(element, html)
        self.assertIn('src="/static/words.js"', html)
        self.assertIn('data-email-verified="true"', html)
        self.assertNotIn('id="verify-banner"', html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("onclick=", html)
        self.assertEqual(self.client.get("/static/words.js").status_code, 200)

    def test_words_page_shows_banner_when_unverified(self):
        self.signup_and_login()
        html = self.client.get("/words").text
        self.assertIn('id="verify-banner"', html)
        self.assertIn('data-email-verified="false"', html)

    def test_member_pages_share_navigation_and_logout(self):
        self.signup_and_login()
        for path in ("/", "/words"):
            html = self.client.get(path).text
            self.assertIn('id="logout-button"', html, path)
            self.assertIn('href="/words"', html, path)

    def test_unknown_page_is_not_api_format(self):
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("error", response.json())


if __name__ == "__main__":
    unittest.main()

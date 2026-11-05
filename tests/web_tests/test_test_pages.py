#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시험 시작, 진행, 기록 화면과 홈의 최근 시험 테스트 (FR-TEST-01, FR-TEST-07, FR-HOME-01)
# 파일 위치: tests/web_tests/test_test_pages.py

import unittest

from web_tests.test_tests_api import TestsTestCase


class TestPagesTest(TestsTestCase):
    def test_pages_require_login_and_keep_address(self):
        anonymous = self.make_auth_client(ip="anonymous")
        for path, expected in (
            ("/tests", "/login?next=%2Ftests"),
            ("/tests/5", "/login?next=%2Ftests%2F5"),
            ("/tests/history", "/login?next=%2Ftests%2Fhistory"),
        ):
            with self.subTest(path=path):
                response = anonymous.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], expected)

    def test_start_page_uses_settings_defaults_and_rules(self):
        self.client.put(
            "/api/v1/settings",
            json={"daily_new_count": 1, "daily_review_count": 0, "daily_wrong_count": 0,
                  "wrong_threshold": 1, "test_format": "subjective", "test_direction": "both"},
            headers=self.headers,
        )
        self.add_words()
        html = self.client.get("/tests").text
        self.assertIn('<option value="subjective" selected>주관식</option>', html)
        self.assertIn('<option value="both" selected>양방향</option>', html)
        self.assertIn('data-word-count="5"', html)
        self.assertIn('data-multiple-minimum="4"', html)
        self.assertIn('min="1" max="200" value="10"', html)
        self.assertIn('data-has-open="false"', html)
        self.assertIn('src="/static/tests.js"', html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("style=", html)

    def test_start_page_offers_open_test(self):
        self.add_words()
        attempt = self.start_ok()
        html = self.client.get("/tests").text
        self.assertIn(f'href="/tests/{attempt["id"]}"', html)
        self.assertIn('data-has-open="true"', html)

    def test_expired_open_test_is_not_offered(self):
        self.add_words()
        attempt = self.start_ok()
        self.expire(attempt["id"])
        html = self.client.get("/tests").text
        self.assertNotIn('id="continue-test"', html)
        self.assertIn('data-has-open="false"', html)

    def test_take_page_has_no_answers_in_html(self):
        self.add_words({"apple": "사과"})
        attempt = self.start_ok("subjective", "ko_en", count=1)
        html = self.client.get(f"/tests/{attempt['id']}").text
        self.assertIn(f'data-attempt-id="{attempt["id"]}"', html)
        self.assertIn('src="/static/test_take.js"', html)
        self.assertNotIn("apple", html)
        self.assertNotIn("<script>", html)
        self.assertEqual(self.client.get("/static/test_take.js").status_code, 200)

    def test_submitted_test_page_shows_score(self):
        self.add_words()
        attempt = self.start_ok(count=2)
        self.submit(attempt["id"], self.right_answers(attempt))
        html = self.client.get(f"/tests/{attempt['id']}").text
        self.assertIn('id="test-finished"', html)
        self.assertIn("2문항 중 2개를 맞혔습니다 (100%)", html)
        self.assertNotIn("test_take.js", html)

    def test_expired_test_page_explains(self):
        self.add_words()
        attempt = self.start_ok()
        self.expire(attempt["id"])
        html = self.client.get(f"/tests/{attempt['id']}").text
        self.assertIn('id="test-expired"', html)
        self.assertNotIn("test_take.js", html)

    def test_missing_or_other_member_test_page_is_404(self):
        self.add_words()
        attempt = self.start_ok()
        other = self.make_auth_client(ip="other")
        self.verified_member("other@example.com", client=other)
        self.assertEqual(other.get(f"/tests/{attempt['id']}").status_code, 404)
        for path in ("/tests/999999", "/tests/abc", f"/tests/{10**30}"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_history_page(self):
        self.assertIn('id="history-empty"', self.client.get("/tests/history").text)
        self.add_words()
        attempt = self.start_ok("multiple", "ko_en", count=2)
        self.submit(attempt["id"], self.right_answers(attempt))
        html = self.client.get("/tests/history").text
        self.assertIn("시험 1회, 전체 정답률 100%", html)
        self.assertIn(
            '<td data-label="형식">객관식</td><td data-label="방향">한→영</td>'
            '<td data-label="점수">2/2</td><td data-label="정답률">100%</td>',
            html,
        )
        self.assertIn('<a href="/tests/history" aria-current="page">', html)
        self.assertNotIn("<script>", html)

    def test_history_page_shows_korea_time_and_pages(self):
        self.add_words()
        for _ in range(21):
            self.submit(self.start_ok(count=1)["id"], [])
        first = self.client.get("/tests/history").text
        self.assertEqual(first.count('<tr><td data-label="날짜">'), 20)
        self.assertIn('href="/tests/history?page=2"', first)
        second = self.client.get("/tests/history?page=2").text
        self.assertEqual(second.count('<tr><td data-label="날짜">'), 1)
        self.assertIn('href="/tests/history?page=1"', second)
        for bad_page in ("abc", "0", "-1", "9" * 40):
            with self.subTest(bad_page=bad_page):
                self.assertEqual(self.client.get(f"/tests/history?page={bad_page}").status_code, 200)

    def test_home_shows_latest_test(self):
        html = self.client.get("/").text
        self.assertIn('id="latest-test-empty"', html)
        self.add_words()
        attempt = self.start_ok("subjective", "en_ko", count=2)
        self.submit(attempt["id"], [])
        html = self.client.get("/").text
        self.assertIn('id="latest-test"', html)
        self.assertIn("주관식, 영→한, 2문항 중 0개 (0%)", html)

    def test_menu_links_to_test_pages(self):
        for path in ("/", "/words", "/tests", "/tests/history", "/settings"):
            with self.subTest(path=path):
                html = self.client.get(path).text
                self.assertIn('href="/tests"', html)
                self.assertIn('href="/tests/history"', html)


if __name__ == "__main__":
    unittest.main()

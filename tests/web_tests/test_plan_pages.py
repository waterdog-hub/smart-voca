#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 홈, 암기, 일차 보기 화면 테스트 (FR-HOME-01, FR-PLAN-05, FR-MEM-05)
# 파일 위치: tests/web_tests/test_plan_pages.py

import unittest

from web_tests.test_plans_api import PlansTestCase


class PlanPagesTest(PlansTestCase):
    def test_pages_require_login_and_keep_address(self):
        anonymous = self.make_auth_client(ip="anonymous")
        for path, expected in (
            ("/memorize", "/login?next=%2Fmemorize"),
            ("/plans?day=2", "/login?next=%2Fplans%3Fday%3D2"),
        ):
            with self.subTest(path=path):
                response = anonymous.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], expected)

    def test_home_guides_through_each_state(self):
        html = self.client.get("/").text
        self.assertIn('data-state="no-words"', html)
        self.assertNotIn("data-create-plan", html)
        self.add_words("a1", "a2")
        self.use_small_day(daily_new_count=1, daily_review_count=0)
        html = self.client.get("/").text
        self.assertIn('data-state="ready"', html)
        self.assertIn("data-create-plan", html)
        plan = self.create_ok()
        html = self.client.get("/").text
        self.assertIn('data-state="in-progress"', html)
        self.assertIn('id="continue-link"', html)
        self.assertNotIn("data-create-plan", html)
        self.finish_day(plan)
        html = self.client.get("/").text
        self.assertIn("1일차를 모두 외웠습니다", html)
        self.assertIn("전체 2개 중 1개를 외웠습니다", html)

    def test_memorize_page_without_plan_guides_to_home(self):
        html = self.client.get("/memorize").text
        self.assertIn('id="memorize-empty"', html)
        self.assertNotIn('id="memorize-app"', html)

    def test_memorize_page_defaults_to_current_day(self):
        self.add_words("a1", "a2")
        self.use_small_day(daily_new_count=1)
        self.finish_day(self.create_ok())
        self.create_ok()
        html = self.client.get("/memorize").text
        self.assertIn('data-day="2" data-is-current="true"', html)
        self.assertIn('<option value="1" >1일차</option>', html)
        self.assertIn('<option value="2" selected>2일차 (현재)</option>', html)
        self.assertNotIn('id="review-notice"', html)
        for attribute in ('id="show-meaning"', 'id="remember-button"', 'id="again-button"',
                          'src="/static/memorize.js"'):
            self.assertIn(attribute, html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("style=", html)

    def test_memorize_page_past_day_is_review_mode(self):
        self.add_words("a1", "a2")
        self.use_small_day(daily_new_count=1)
        self.finish_day(self.create_ok())
        self.create_ok()
        html = self.client.get("/memorize?day=1").text
        self.assertIn('data-day="1" data-is-current="false"', html)
        self.assertIn('id="review-notice"', html)

    def test_invalid_day_falls_back_to_current(self):
        self.add_words("a1")
        self.create_ok()
        for query in ("abc", "99", "0", "-1", "9" * 40):
            with self.subTest(query=query):
                for path in ("/memorize", "/plans"):
                    response = self.client.get(f"{path}?day={query}")
                    self.assertEqual(response.status_code, 200)
                self.assertIn('data-day="1"', self.client.get(f"/memorize?day={query}").text)

    def test_plans_page_is_read_only_list(self):
        self.add_words("<b>a1</b>", "a2")
        self.use_small_day(daily_new_count=1)
        plan = self.create_ok()
        self.patch(plan["items"][0]["id"], done=True)
        html = self.client.get("/plans?day=1").text
        self.assertIn("&lt;b&gt;a1&lt;/b&gt;", html)
        self.assertNotIn("<b>a1</b>", html)
        self.assertIn("<td>신규</td><td>외움</td>", html)
        self.assertIn('<option value="1" selected>1일차 (1/1)</option>', html)
        self.assertIn('<a href="/memorize" aria-current="page">', html)
        self.assertNotIn("<script>", html)

    def test_plans_page_without_plan(self):
        self.assertIn('id="plans-empty"', self.client.get("/plans").text)


if __name__ == "__main__":
    unittest.main()

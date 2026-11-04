#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시험 기록과 권한 API 테스트 (FR-TEST-07, 회원 간 차단)
# 파일 위치: tests/web_tests/test_tests_records.py

import unittest

from web_tests.test_tests_api import HISTORY_API, TESTS_API, TestsTestCase


class HistoryTest(TestsTestCase):
    def test_empty_history(self):
        self.assertEqual(
            self.client.get(HISTORY_API).json(),
            {"items": [], "total_count": 0, "overall_percent": 0},
        )

    def test_history_is_newest_first_with_weighted_accuracy(self):
        # 전체 정답률은 문항 수로 가중한다 (D-19): (1 + 0) / (1 + 3) = 25%
        self.add_words()
        first = self.start_ok(count=1)
        self.submit(first["id"], self.right_answers(first))
        second = self.start_ok(count=3)
        self.submit(second["id"], self.wrong_answers(second))
        body = self.client.get(HISTORY_API).json()
        self.assertEqual(body["total_count"], 2)
        self.assertEqual(body["overall_percent"], 25)
        self.assertEqual([(i["total"], i["score"], i["percent"]) for i in body["items"]],
                         [(3, 0, 0), (1, 1, 100)])

    def test_paging(self):
        self.add_words()
        for _ in range(3):
            self.submit(self.start_ok(count=1)["id"], [])
        body = self.client.get(HISTORY_API, params={"limit": 2, "offset": 2}).json()
        self.assertEqual((len(body["items"]), body["total_count"]), (1, 3))
        self.assertEqual(self.client.get(HISTORY_API, params={"limit": 0}).status_code, 400)
        self.assertEqual(self.client.get(HISTORY_API, params={"limit": 201}).status_code, 400)

    def test_unsubmitted_test_is_not_in_history(self):
        self.add_words()
        self.start_ok()
        self.assertEqual(self.client.get(HISTORY_API).json()["total_count"], 0)


class TestPermissionTest(TestsTestCase):
    def test_reads_require_login(self):
        anonymous = self.make_auth_client(ip="anonymous")
        for path in (HISTORY_API, f"{TESTS_API}/1"):
            with self.subTest(path=path):
                self.assertEqual(anonymous.get(path).status_code, 401)

    def test_writes_require_csrf_token(self):
        self.add_words()
        attempt = self.start_ok()
        payload = {"test_format": "multiple", "test_direction": "en_ko", "count": 1}
        for response in (
            self.client.post(TESTS_API, json=payload),
            self.client.post(f"{TESTS_API}/{attempt['id']}/submit", json={"answers": []}),
        ):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")

    def test_unverified_member_can_read_but_not_write(self):
        client = self.make_auth_client(ip="unverified")
        token = self.signup_and_login("unverified@example.com", client=client)
        self.assertEqual(client.get(HISTORY_API).status_code, 200)
        response = client.post(
            TESTS_API,
            json={"test_format": "subjective", "test_direction": "en_ko", "count": 1},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "EMAIL_NOT_VERIFIED")

    def test_other_member_test_is_hidden(self):
        self.add_words()
        attempt = self.start_ok()
        other = self.make_auth_client(ip="other")
        other_headers = self.verified_member("other@example.com", client=other)
        self.assertEqual(other.get(f"{TESTS_API}/{attempt['id']}").status_code, 404)
        response = self.submit(attempt["id"], self.wrong_answers(attempt), client=other, headers=other_headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.wrong_counts(), {})
        self.assertEqual(self.client.get(f"{TESTS_API}/{attempt['id']}").status_code, 200)

    def test_history_is_separate_per_member(self):
        self.add_words()
        self.submit(self.start_ok(count=1)["id"], [])
        other = self.make_auth_client(ip="other")
        self.verified_member("other@example.com", client=other)
        self.assertEqual(other.get(HISTORY_API).json()["total_count"], 0)


if __name__ == "__main__":
    unittest.main()

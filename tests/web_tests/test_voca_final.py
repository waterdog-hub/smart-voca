#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-25 - smart-voca - 기말 과제 요건 테스트: 학교 서버 모드, 단어 직접 등록·CSV, 이력 표, 통계
# 파일 위치: tests/web_tests/test_voca_final.py
# 관련 요구사항: VOCA-FR-001~004, 014, 026, 031~034, VOCA-NFR-003, VOCA-SUB-035·036

import unittest

from sqlalchemy import inspect, select

from web.app import create_app
from web.db.base import make_engine
from web.db.tables import MemorizeLog, TestResult
from web.settings import Settings
from web_tests.support import AuthTestCase, WebTestCase
from web_tests.test_tests_api import TestsTestCase

WORDS_API = "/api/v1/words"


class SchoolSettingsTest(WebTestCase):
    def test_db_path_becomes_sqlite_url(self):
        settings = Settings(app_env="school", db_path="/data/voca.db", secret_key="s", _env_file=None)
        self.assertEqual(settings.database_url, "sqlite:////data/voca.db")

    def test_school_mode_needs_no_https_and_verifies_at_signup(self):
        settings = Settings(app_env="school", db_path="/data/voca.db", secret_key="short", _env_file=None)
        self.assertTrue(settings.auto_verifies_email)
        self.assertFalse(settings.uses_secure_cookie)
        self.assertGreaterEqual(len(settings.auth_hash_key), 32)

    def test_same_secret_gives_same_key(self):
        first = Settings(app_env="school", db_path="/data/voca.db", secret_key="abc", _env_file=None)
        second = Settings(app_env="school", db_path="/data/voca.db", secret_key="abc", _env_file=None)
        self.assertEqual(first.auth_hash_key, second.auth_hash_key)

    def test_generated_key_is_kept_next_to_db(self):
        db_path = str(self.temp_path / "voca.db")
        first = Settings(app_env="school", db_path=db_path, _env_file=None)
        second = Settings(app_env="school", db_path=db_path, _env_file=None)
        self.assertEqual(first.auth_hash_key, second.auth_hash_key)

    def test_missing_database_is_an_error(self):
        with self.assertRaises(ValueError):
            Settings(app_env="local", _env_file=None)

    def test_school_app_creates_tables_and_wordbooks_on_start(self):
        db_path = (self.temp_path / "school.db").as_posix()
        app = create_app(Settings(app_env="school", db_path=db_path, secret_key="k", _env_file=None))
        from fastapi.testclient import TestClient

        with TestClient(app, base_url="http://testserver") as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertIn('rel="home" href="/"', client.get("/login").text)
        engine = make_engine(f"sqlite:///{db_path}")
        tables = set(inspect(engine).get_table_names())
        engine.dispose()
        self.assertTrue({"words", "memorize_logs", "test_results", "wordbooks"} <= tables)


class WordWriteTest(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.headers = self.verified_member()

    def add(self, word, meaning):
        return self.client.post(WORDS_API, json={"word": word, "meaning": meaning}, headers=self.headers)

    def words(self, **params):
        return self.client.get(WORDS_API, params=params).json()

    def test_add_update_delete(self):
        created = self.add(" apple ", "사과")
        self.assertEqual(created.status_code, 201, created.text)
        word_id = created.json()["id"]
        updated = self.client.put(f"{WORDS_API}/{word_id}", json={"word": "Apple", "meaning": "사과/애플"}, headers=self.headers)
        self.assertEqual(updated.json()["meaning"], "사과/애플")
        self.assertEqual(self.words(q="애플")["total"], 1)
        self.assertEqual(self.client.delete(f"{WORDS_API}/{word_id}", headers=self.headers).status_code, 204)
        self.assertEqual(self.words()["total"], 0)

    def test_duplicate_ignores_case(self):
        self.add("apple", "사과")
        response = self.add("APPLE", "사과")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "WORD_EXISTS")

    def test_blank_is_rejected(self):
        self.assertEqual(self.add("", "뜻").status_code, 400)

    def test_write_needs_csrf(self):
        self.assertEqual(self.client.post(WORDS_API, json={"word": "a", "meaning": "b"}).status_code, 403)

    def test_import_provided_csv_format(self):
        self.add("apple", "사과")
        raw = "﻿영단어,뜻\napple,다른 뜻\nbanana,바나나\nBanana,중복\n,빈칸\ncherry,체리\n".encode("utf-8")
        response = self.client.post(
            f"{WORDS_API}/import", files={"file": ("words.csv", raw, "text/csv")}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            (body["added"], body["skipped_existing"], body["skipped_duplicate"], body["invalid_count"]),
            (2, 1, 1, 1),
        )
        # 이미 있던 단어의 뜻은 바꾸지 않는다
        apple = [item for item in self.words()["items"] if item["word"] == "apple"][0]
        self.assertEqual(apple["meaning"], "사과")

    def test_other_member_cannot_touch_my_word(self):
        word_id = self.add("apple", "사과").json()["id"]
        other = self.make_auth_client(ip="other")
        other_headers = self.verified_member("other@example.com", client=other)
        response = other.put(f"{WORDS_API}/{word_id}", json={"word": "x", "meaning": "y"}, headers=other_headers)
        self.assertEqual(response.status_code, 404)


class HistoryTablesTest(TestsTestCase):
    def test_submit_writes_one_result_per_question(self):
        self.add_words()
        attempt = self.start_ok(count=3)
        self.submit(attempt["id"], self.right_answers(attempt))
        with self.db() as db:
            rows = list(db.scalars(select(TestResult)))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.is_correct and row.answered for row in rows))
        self.assertEqual({row.test_format for row in rows}, {"multiple"})

    def test_stats_page_lists_wrong_words(self):
        self.add_words()
        attempt = self.start_ok(count=3)
        self.submit(attempt["id"], self.wrong_answers(attempt))
        html = self.client.get("/stats").text
        self.assertIn('id="stats-wrong-table"', html)
        self.assertIn('id="stats-sessions"', html)

    def test_memorize_writes_log(self):
        self.add_words()
        self.assertEqual(self.client.post("/api/v1/plans", headers=self.headers).status_code, 201)
        day = self.client.get("/api/v1/plans/1").json()
        item_id = day["items"][0]["id"]
        self.client.patch(f"/api/v1/plan-items/{item_id}", json={"done": True}, headers=self.headers)
        with self.db() as db:
            logs = list(db.scalars(select(MemorizeLog)))
        self.assertEqual([(log.day, log.action) for log in logs], [(1, "done")])


if __name__ == "__main__":
    unittest.main()

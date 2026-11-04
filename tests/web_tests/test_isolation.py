#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원 A가 회원 B의 단어에 접근하지 못하는지 확인한다 (D-A09)
# 파일 위치: tests/web_tests/test_isolation.py

import unittest

from web_tests.support import AuthTestCase

from sqlalchemy import select

from web.db.tables import Word

WORDS_API = "/api/v1/words"


class WordIsolationTest(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.owner_headers = self.verified_member("owner@example.com")
        response = self.client.post(
            WORDS_API, json={"word": "secret", "meaning": "비밀 뜻"}, headers=self.owner_headers
        )
        self.owner_word_id = response.json()["id"]
        self.other = self.make_auth_client()
        self.other_headers = self.verified_member("other@example.com", client=self.other)

    def assert_owner_word_unchanged(self):
        with self.db() as db:
            row = db.get(Word, self.owner_word_id)
        self.assertEqual(row.word, "secret")
        self.assertEqual(row.meaning, "비밀 뜻")
        self.assertIsNone(row.deleted_at)

    def test_list_search_and_export_show_only_own_words(self):
        self.assertEqual(self.other.get(WORDS_API).json(), {"items": [], "total": 0})
        self.assertEqual(self.other.get(WORDS_API, params={"q": "secret"}).json()["total"], 0)
        self.assertNotIn("secret", self.other.get(f"{WORDS_API}/export").text)

    def test_update_of_other_member_word_returns_404(self):
        response = self.other.patch(
            f"{WORDS_API}/{self.owner_word_id}", json={"word": "stolen"}, headers=self.other_headers
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
        self.assert_owner_word_unchanged()

    def test_404_is_same_as_missing_word(self):
        owned_by_other = self.other.patch(
            f"{WORDS_API}/{self.owner_word_id}", json={"word": "x"}, headers=self.other_headers
        )
        missing = self.other.patch(
            f"{WORDS_API}/999999", json={"word": "x"}, headers=self.other_headers
        )
        self.assertEqual(owned_by_other.json(), missing.json())

    def test_delete_of_other_member_word_changes_nothing(self):
        response = self.other.post(
            f"{WORDS_API}/delete", json={"ids": [self.owner_word_id]}, headers=self.other_headers
        )
        self.assertEqual(response.json(), {"deleted": 0})
        self.assert_owner_word_unchanged()

    def test_same_word_is_allowed_for_different_members(self):
        response = self.other.post(
            WORDS_API, json={"word": "secret", "meaning": "내 뜻"}, headers=self.other_headers
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()["id"], self.owner_word_id)
        self.assert_owner_word_unchanged()

    def test_import_does_not_touch_other_member_words(self):
        content = "word,meaning\nsecret,덮어쓰기 시도\n".encode("utf-8")
        response = self.other.post(
            f"{WORDS_API}/import", files={"file": ("w.csv", content)}, headers=self.other_headers
        )
        self.assertEqual(response.json()["added"], 1)
        self.assert_owner_word_unchanged()

    def test_deleted_word_of_other_member_is_not_revived(self):
        self.client.post(
            f"{WORDS_API}/delete", json={"ids": [self.owner_word_id]}, headers=self.owner_headers
        )
        response = self.other.post(
            WORDS_API, json={"word": "secret", "meaning": "내 뜻"}, headers=self.other_headers
        )
        self.assertNotEqual(response.json()["id"], self.owner_word_id)
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(Word)).all()), 2)
            self.assertIsNotNone(db.get(Word, self.owner_word_id).deleted_at)

    def test_csrf_token_of_other_member_is_rejected(self):
        response = self.client.post(
            WORDS_API, json={"word": "a", "meaning": "b"}, headers=self.other_headers
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")


if __name__ == "__main__":
    unittest.main()

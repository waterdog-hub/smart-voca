#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 회원 A가 회원 B의 단어와 담은 단어장에 접근하지 못하는지 확인한다 (D-A09)
# 파일 위치: tests/web_tests/test_isolation.py

import unittest

from web_tests.support import AuthTestCase

from sqlalchemy import select

from web.db.tables import UserWordbook, Word

WORDS_API = "/api/v1/words"
WORDBOOKS_API = "/api/v1/wordbooks"


class WordIsolationTest(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.owner_headers = self.verified_member("owner@example.com")
        self.wordbook_id = self.insert_wordbook("shared", {"secret": "공용 뜻", "other": "다른 단어"})
        added = self.client.post(f"{WORDBOOKS_API}/{self.wordbook_id}/add", headers=self.owner_headers)
        self.assertEqual(added.json(), {"added": 2, "already_had": 0})
        with self.db() as db:
            self.owner_word_id = db.scalar(select(Word.id).where(Word.word_key == "secret"))
        self.other = self.make_auth_client()
        self.other_headers = self.verified_member("other@example.com", client=self.other)

    def assert_owner_word_unchanged(self):
        with self.db() as db:
            row = db.get(Word, self.owner_word_id)
        self.assertEqual((row.word, row.meaning), ("secret", "공용 뜻"))
        self.assertIsNone(row.deleted_at)

    def test_list_and_search_show_only_own_words(self):
        self.assertEqual(self.other.get(WORDS_API).json(), {"items": [], "total": 0})
        self.assertEqual(self.other.get(WORDS_API, params={"q": "secret"}).json()["total"], 0)

    def test_wordbook_list_shows_only_own_added_state(self):
        owner_view = self.client.get(WORDBOOKS_API).json()["items"][0]
        other_view = self.other.get(WORDBOOKS_API).json()["items"][0]
        self.assertTrue(owner_view["added"])
        self.assertFalse(other_view["added"])
        self.assertIsNone(other_view["added_at"])

    def test_other_member_remove_changes_nothing_of_owner(self):
        response = self.other.post(
            f"{WORDBOOKS_API}/{self.wordbook_id}/remove", headers=self.other_headers
        )
        self.assertEqual(response.json(), {"removed": 0, "kept": 0})
        self.assert_owner_word_unchanged()
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(UserWordbook)).all()), 1)

    def test_other_member_add_and_remove_only_touch_own_words(self):
        added = self.other.post(f"{WORDBOOKS_API}/{self.wordbook_id}/add", headers=self.other_headers)
        self.assertEqual(added.json(), {"added": 2, "already_had": 0})
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(Word)).all()), 4)
        self.other.post(f"{WORDBOOKS_API}/{self.wordbook_id}/remove", headers=self.other_headers)
        self.assert_owner_word_unchanged()
        self.assertEqual(self.client.get(WORDS_API).json()["total"], 2)

    def test_deleted_word_of_other_member_is_not_revived(self):
        self.client.post(f"{WORDBOOKS_API}/{self.wordbook_id}/remove", headers=self.owner_headers)
        self.other.post(f"{WORDBOOKS_API}/{self.wordbook_id}/add", headers=self.other_headers)
        with self.db() as db:
            rows = db.scalars(select(Word).where(Word.word_key == "secret")).all()
            self.assertEqual(len(rows), 2)
            self.assertIsNotNone(db.get(Word, self.owner_word_id).deleted_at)

    def test_csrf_token_of_other_member_is_rejected(self):
        response = self.client.post(
            f"{WORDBOOKS_API}/{self.wordbook_id}/add", headers=self.other_headers
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")


if __name__ == "__main__":
    unittest.main()

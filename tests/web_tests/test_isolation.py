#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 회원 A가 회원 B의 단어, 담은 단어장, 진도, 암기 기록에 접근하지 못하는지 확인한다 (D-A09, NFR-SEC-07)
# 파일 위치: tests/web_tests/test_isolation.py

import unittest

from web_tests.support import AuthTestCase

from sqlalchemy import select

from web.db.tables import PlanItem, StudyRecord, UserWordbook, Word

WORDS_API = "/api/v1/words"
WORDBOOKS_API = "/api/v1/wordbooks"
PLANS_API = "/api/v1/plans"
ITEMS_API = "/api/v1/plan-items"
PROGRESS_API = "/api/v1/progress"


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


class PlanIsolationTest(AuthTestCase):
    """회원 A의 진도 항목과 암기 기록을 회원 B가 보거나 바꾸지 못한다. 없는 자원과 같은 404로 답한다."""

    def setUp(self):
        super().setUp()
        self.owner_headers = self.verified_member("owner@example.com")
        self.insert_words({"alpha": "첫째", "bravo": "둘째"}, email="owner@example.com")
        created = self.client.post(PLANS_API, headers=self.owner_headers)
        self.assertEqual(created.status_code, 201, created.text)
        self.owner_item_ids = [item["id"] for item in created.json()["items"]]
        self.other = self.make_auth_client()
        self.other_headers = self.verified_member("other@example.com", client=self.other)

    def test_other_member_cannot_mark_an_item_and_gets_the_same_404_as_a_missing_item(self):
        owner_item = self.owner_item_ids[0]
        missing_item = max(self.owner_item_ids) + 1000
        stolen = self.other.patch(f"{ITEMS_API}/{owner_item}", json={"done": True}, headers=self.other_headers)
        missing = self.other.patch(f"{ITEMS_API}/{missing_item}", json={"done": True}, headers=self.other_headers)
        self.assertEqual((stolen.status_code, missing.status_code), (404, 404))
        self.assertEqual(stolen.json(), missing.json())
        with self.db() as db:
            self.assertEqual(db.scalars(select(PlanItem.done).where(PlanItem.id == owner_item)).one(), False)
            self.assertEqual(db.scalars(select(StudyRecord)).all(), [])

    def test_other_member_cannot_send_an_item_to_the_back(self):
        response = self.other.patch(
            f"{ITEMS_API}/{self.owner_item_ids[0]}", json={"later": True}, headers=self.other_headers
        )
        self.assertEqual(response.status_code, 404)

    def test_other_member_sees_no_plans_and_no_progress_of_the_owner(self):
        self.assertEqual(self.other.get(PLANS_API).json()["items"], [])
        self.assertEqual(self.other.get(f"{PLANS_API}/1").status_code, 404)
        progress = self.other.get(PROGRESS_API).json()
        self.assertEqual(progress["total_words"], 0)
        self.assertEqual(progress["memorized_words"], 0)

    def test_other_member_creating_a_plan_does_not_touch_the_owners_plan(self):
        self.assertEqual(self.other.post(PLANS_API, headers=self.other_headers).status_code, 409)
        with self.db() as db:
            ids = db.scalars(select(PlanItem.id).order_by(PlanItem.id)).all()
        self.assertEqual(ids, sorted(self.owner_item_ids))


if __name__ == "__main__":
    unittest.main()

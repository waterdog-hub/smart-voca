#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 공용 단어장 목록, 담기, 제외 API 테스트 (FR-BOOK-01~03, 결정 D-WB01~D-WB07)
# 파일 위치: tests/web_tests/test_wordbooks_api.py

import unittest
from unittest import mock

from web_tests.support import AuthTestCase

from sqlalchemy import select

from web.db.tables import PlanItem, StudyRecord, User, UserWordbook, Word
from web.repositories import word_repository

WORDBOOKS_API = "/api/v1/wordbooks"
WORDS_API = "/api/v1/words"
PLANS_API = "/api/v1/plans"
BOOK_A = {"apple": "사과", "river": "강", "tree": "나무"}
BOOK_B = {"Apple": "애플", "stone": "돌"}


class WordbookTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.headers = self.verified_member()
        self.book_a = self.insert_wordbook("book-a", BOOK_A)
        self.book_b = self.insert_wordbook("book-b", BOOK_B)

    def add(self, wordbook_id, expected=200):
        response = self.client.post(f"{WORDBOOKS_API}/{wordbook_id}/add", headers=self.headers)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def remove(self, wordbook_id, expected=200):
        response = self.client.post(f"{WORDBOOKS_API}/{wordbook_id}/remove", headers=self.headers)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def my_words(self):
        return {item["word"] for item in self.client.get(WORDS_API, params={"limit": 200}).json()["items"]}

    def stored_word(self, word_key):
        with self.db() as db:
            return db.scalar(select(Word).where(Word.word_key == word_key))

    def add_plan_item_and_record(self, word_key):
        with self.db() as db:
            user_id = db.scalar(select(User.id))
            word_id = db.scalar(select(Word.id).where(Word.word_key == word_key))
            db.add(PlanItem(user_id=user_id, day=1, word_id=word_id, assigned_type="new", position=0))
            db.add(StudyRecord(user_id=user_id, word_id=word_id, wrong_count=3))
            db.commit()
            return word_id


class ListWordbooksTest(WordbookTestCase):
    def test_list_shows_books_in_order_with_counts_and_samples(self):
        items = self.client.get(WORDBOOKS_API).json()["items"]
        self.assertEqual([item["title"] for item in items], ["book-a 단어장", "book-b 단어장"])
        first = items[0]
        self.assertEqual(first["word_count"], 3)
        self.assertEqual(first["sample_words"], ["apple", "river", "tree"])
        self.assertEqual(first["description"], "book-a 설명")
        self.assertEqual(first["source_note"], "테스트 자료")
        self.assertFalse(first["added"])
        self.assertIsNone(first["added_at"])

    def test_sample_words_are_limited_to_first_five_in_order(self):
        self.insert_wordbook("long", {f"w{number}": "뜻" for number in range(1, 9)})
        long_book = self.client.get(WORDBOOKS_API).json()["items"][2]
        self.assertEqual(long_book["word_count"], 8)
        self.assertEqual(long_book["sample_words"], ["w1", "w2", "w3", "w4", "w5"])

    def test_added_state_and_time_appear_after_adding(self):
        self.add(self.book_a)
        items = self.client.get(WORDBOOKS_API).json()["items"]
        self.assertTrue(items[0]["added"])
        self.assertTrue(items[0]["added_at"].endswith("Z"))
        self.assertFalse(items[1]["added"])

    def test_list_requires_login(self):
        self.client.post("/api/v1/auth/logout", headers=self.headers)
        self.assertEqual(self.client.get(WORDBOOKS_API).status_code, 401)


class AddWordbookTest(WordbookTestCase):
    def test_add_copies_entries_to_my_words(self):
        self.assertEqual(self.add(self.book_a), {"added": 3, "already_had": 0})
        self.assertEqual(self.my_words(), set(BOOK_A))
        self.assertEqual(self.stored_word("river").meaning, "강")

    def test_add_twice_changes_nothing_the_second_time(self):
        self.add(self.book_a)
        self.assertEqual(self.add(self.book_a), {"added": 0, "already_had": 3})
        self.assertEqual(len(self.my_words()), 3)
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(UserWordbook)).all()), 1)

    def test_existing_word_keeps_its_meaning(self):
        # 이미 학습 중인 단어의 뜻은 단어장이 바꾸지 않는다 (D-WB06)
        self.insert_words({"apple": "내 뜻"})
        self.assertEqual(self.add(self.book_a), {"added": 2, "already_had": 1})
        self.assertEqual(self.stored_word("apple").meaning, "내 뜻")

    def test_words_differing_only_in_case_are_the_same_word(self):
        self.add(self.book_a)
        self.assertEqual(self.add(self.book_b), {"added": 1, "already_had": 1})
        self.assertEqual(self.stored_word("apple").word, "apple")
        self.assertEqual(self.stored_word("apple").meaning, "사과")

    def test_re_adding_removed_word_keeps_id_and_record(self):
        # 제외했다가 다시 담으면 이전 학습 기록을 이어 간다 (FR-WORD-05)
        self.add(self.book_a)
        word_id = self.add_plan_item_and_record("apple")
        self.remove(self.book_a)
        self.add(self.book_a)
        row = self.stored_word("apple")
        self.assertEqual(row.id, word_id)
        self.assertIsNone(row.deleted_at)
        with self.db() as db:
            self.assertEqual(db.scalar(select(StudyRecord.wrong_count)), 3)

    def test_added_words_are_used_for_a_plan(self):
        self.add(self.book_a)
        response = self.client.post(PLANS_API, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual({item["word"] for item in response.json()["items"]}, set(BOOK_A))

    def test_missing_wordbook_returns_404(self):
        error = self.add(999999, expected=404)["error"]
        self.assertEqual(error["code"], "NOT_FOUND")
        self.assertEqual(self.my_words(), set())

    def test_out_of_range_id_returns_400(self):
        for wordbook_id in (0, -1, 2**31):
            with self.subTest(wordbook_id=wordbook_id):
                response = self.client.post(
                    f"{WORDBOOKS_API}/{wordbook_id}/add", headers=self.headers
                )
                self.assertEqual(response.status_code, 400, response.text)

    def test_losing_a_race_changes_nothing_and_returns_409(self):
        # 목록을 읽은 직후 같은 단어가 다른 요청으로 들어온 상황을 재현한다
        original = word_repository.list_all_words_including_deleted

        def with_competing_insert(db, user_id):
            rows = original(db, user_id)
            self.insert_words({"apple": "경쟁"})
            return rows

        with mock.patch.object(
            word_repository, "list_all_words_including_deleted", with_competing_insert
        ):
            error = self.add(self.book_a, expected=409)["error"]
        self.assertEqual(error["code"], "WORDBOOK_BUSY")
        self.assertEqual(self.my_words(), {"apple"})
        with self.db() as db:
            self.assertEqual(db.scalars(select(UserWordbook)).all(), [])


class RemoveWordbookTest(WordbookTestCase):
    def test_remove_deletes_words_and_plan_items_but_keeps_records(self):
        self.add(self.book_a)
        word_id = self.add_plan_item_and_record("apple")
        self.assertEqual(self.remove(self.book_a), {"removed": 3, "kept": 0})
        self.assertEqual(self.my_words(), set())
        with self.db() as db:
            self.assertIsNotNone(db.get(Word, word_id).deleted_at)
            self.assertEqual(db.scalars(select(PlanItem)).all(), [])
            self.assertEqual(len(db.scalars(select(StudyRecord)).all()), 1)
            self.assertEqual(db.scalars(select(UserWordbook)).all(), [])
        self.assertFalse(self.client.get(WORDBOOKS_API).json()["items"][0]["added"])

    def test_words_in_another_added_book_are_kept(self):
        # 겹치는 단어는 남은 단어장에 있으므로 지우지 않는다 (D-WB03)
        self.add(self.book_a)
        self.add(self.book_b)
        self.assertEqual(self.remove(self.book_a), {"removed": 2, "kept": 1})
        self.assertEqual(self.my_words(), {"apple", "stone"})

    def test_removing_the_other_book_keeps_the_shared_word_too(self):
        self.add(self.book_a)
        self.add(self.book_b)
        self.assertEqual(self.remove(self.book_b), {"removed": 1, "kept": 1})
        self.assertEqual(self.my_words(), set(BOOK_A))

    def test_removing_both_books_removes_everything(self):
        self.add(self.book_a)
        self.add(self.book_b)
        self.remove(self.book_a)
        self.assertEqual(self.remove(self.book_b), {"removed": 2, "kept": 0})
        self.assertEqual(self.my_words(), set())

    def test_remove_of_book_not_added_changes_nothing(self):
        self.insert_words({"apple": "내 단어"})
        self.assertEqual(self.remove(self.book_a), {"removed": 0, "kept": 0})
        self.assertEqual(self.my_words(), {"apple"})

    def test_remove_twice_is_harmless(self):
        self.add(self.book_a)
        self.remove(self.book_a)
        self.assertEqual(self.remove(self.book_a), {"removed": 0, "kept": 0})

    def test_removed_word_is_not_assigned_to_a_plan(self):
        self.add(self.book_a)
        self.add(self.book_b)
        self.remove(self.book_a)
        response = self.client.post(PLANS_API, headers=self.headers)
        self.assertEqual({item["word"] for item in response.json()["items"]}, {"apple", "stone"})

    def test_missing_wordbook_returns_404(self):
        self.assertEqual(self.remove(999999, expected=404)["error"]["code"], "NOT_FOUND")

    def test_large_book_is_removed_in_chunks(self):
        words = {f"word{number}": "뜻" for number in range(1200)}
        big_book = self.insert_wordbook("big", words)
        self.assertEqual(self.add(big_book), {"added": 1200, "already_had": 0})
        self.assertEqual(self.remove(big_book), {"removed": 1200, "kept": 0})
        self.assertEqual(self.client.get(WORDS_API).json()["total"], 0)


class WordbookPermissionTest(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.book = self.insert_wordbook("book-a", BOOK_A)

    def test_anonymous_gets_401_everywhere(self):
        for method, url in (
            ("GET", WORDBOOKS_API),
            ("POST", f"{WORDBOOKS_API}/{self.book}/add"),
            ("POST", f"{WORDBOOKS_API}/{self.book}/remove"),
        ):
            with self.subTest(method=method, url=url):
                self.assertEqual(self.client.request(method, url).status_code, 401)

    def test_unverified_member_can_read_but_not_write(self):
        headers = {"X-CSRF-Token": self.signup_and_login()}
        self.assertEqual(self.client.get(WORDBOOKS_API).status_code, 200)
        for action in ("add", "remove"):
            with self.subTest(action=action):
                response = self.client.post(f"{WORDBOOKS_API}/{self.book}/{action}", headers=headers)
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()["error"]["code"], "EMAIL_NOT_VERIFIED")

    def test_writes_require_csrf_token(self):
        self.verified_member()
        for action in ("add", "remove"):
            with self.subTest(action=action):
                response = self.client.post(f"{WORDBOOKS_API}/{self.book}/{action}")
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 내 단어 조회 API 테스트와 없앤 쓰기 API 확인 (FR-WORD-06~08, 결정 D-WB04)
# 파일 위치: tests/web_tests/test_words_api.py

import unittest

from web_tests.support import AuthTestCase

WORDS_API = "/api/v1/words"
SAMPLE_WORDS = {"cherry": "체리", "Apple": "사과/애플", "banana": "바나나"}


class WordsTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.verified_member()

    def listing(self, **params):
        response = self.client.get(WORDS_API, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def words_of(self, **params):
        return [item["word"] for item in self.listing(**params)["items"]]


class ListWordsTest(WordsTestCase):
    def test_default_sort_is_word_ascending_ignoring_case(self):
        self.insert_words(SAMPLE_WORDS)
        self.assertEqual(self.words_of(), ["Apple", "banana", "cherry"])

    def test_item_has_id_word_meaning_and_utc_time(self):
        self.insert_words({"apple": "사과"})
        item = self.listing()["items"][0]
        self.assertEqual((item["word"], item["meaning"]), ("apple", "사과"))
        self.assertIsInstance(item["id"], int)
        self.assertTrue(item["created_at"].endswith("Z"))

    def test_sort_options(self):
        self.insert_words(SAMPLE_WORDS)
        self.assertEqual(self.words_of(order="desc"), ["cherry", "banana", "Apple"])
        self.assertEqual(self.words_of(sort="created"), ["cherry", "Apple", "banana"])
        self.assertEqual(self.words_of(sort="created", order="desc"), ["banana", "Apple", "cherry"])
        self.assertEqual(self.words_of(sort="meaning"), ["banana", "Apple", "cherry"])

    def test_search_matches_word_or_meaning_ignoring_case(self):
        self.insert_words(SAMPLE_WORDS)
        self.assertEqual(self.words_of(q="APP"), ["Apple"])
        self.assertEqual(self.words_of(q="애플"), ["Apple"])
        self.assertEqual(self.words_of(q="  체리 "), ["cherry"])
        self.assertEqual(self.listing(q="없는말"), {"items": [], "total": 0})

    def test_search_treats_wildcards_as_plain_text(self):
        self.insert_words({"100%": "백퍼센트", "a_b": "밑줄", "plain": "보통"})
        self.assertEqual(self.words_of(q="%"), ["100%"])
        self.assertEqual(self.words_of(q="_"), ["a_b"])

    def test_paging_returns_total_and_does_not_repeat(self):
        self.insert_words({f"word{index}": "같은 뜻" for index in range(5)})
        page_one = self.listing(limit=2, offset=0, sort="meaning")
        page_two = self.listing(limit=2, offset=2, sort="meaning")
        page_three = self.listing(limit=2, offset=4, sort="meaning")
        self.assertEqual(page_one["total"], 5)
        seen = [item["id"] for page in (page_one, page_two, page_three) for item in page["items"]]
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(set(seen)), 5)

    def test_invalid_query_is_rejected(self):
        for params in (
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
            {"offset": 2**31},
            {"sort": "deleted_at"},
            {"order": "sideways"},
            {"q": "x" * 101},
        ):
            with self.subTest(params=str(params)[:30]):
                response = self.client.get(WORDS_API, params=params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "VALIDATION_FAILED")

    def test_deleted_words_are_hidden(self):
        self.insert_words({"apple": "사과"})
        self.delete_words([self.listing()["items"][0]["id"]])
        self.assertEqual(self.listing()["total"], 0)
        self.assertEqual(self.listing(q="apple")["total"], 0)


class RemovedWriteApiTest(WordsTestCase):
    """회원이 단어를 직접 바꾸는 API는 없다. 단어장 담기·제외만 남았다 (결정 D-WB04)."""

    def test_member_cannot_add_edit_delete_import_or_export(self):
        headers = {"X-CSRF-Token": self.login().json()["csrf_token"]}
        responses = {
            "POST /words": self.client.post(WORDS_API, json={"word": "a", "meaning": "b"}, headers=headers),
            "PATCH /words/1": self.client.patch(f"{WORDS_API}/1", json={"word": "a"}, headers=headers),
            "POST /words/delete": self.client.post(f"{WORDS_API}/delete", json={"ids": [1]}, headers=headers),
            "POST /words/import": self.client.post(
                f"{WORDS_API}/import", files={"file": ("w.csv", b"word,meaning\n")}, headers=headers
            ),
            "GET /words/export": self.client.get(f"{WORDS_API}/export"),
        }
        for name, response in responses.items():
            with self.subTest(name):
                self.assertIn(response.status_code, (404, 405), response.text)


class WordPermissionTest(AuthTestCase):
    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(WORDS_API).status_code, 401)

    def test_unverified_member_can_read(self):
        self.signup_and_login()
        self.assertEqual(self.client.get(WORDS_API).status_code, 200)


if __name__ == "__main__":
    unittest.main()

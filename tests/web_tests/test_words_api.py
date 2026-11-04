#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 단어 조회, 추가, 수정, 삭제 API 테스트 (D-24, D-W07, D-W08, D-12)
# 파일 위치: tests/web_tests/test_words_api.py

import unittest
from unittest import mock

from web_tests.support import AuthTestCase

from sqlalchemy import select

from web.db.tables import PlanItem, StudyRecord, User, UserSetting, Word
from web.repositories import word_repository

WORDS_API = "/api/v1/words"
DELETE_API = "/api/v1/words/delete"


class WordsTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.headers = self.verified_member()

    def add(self, word="apple", meaning="사과", client=None, headers=None):
        response = (client or self.client).post(
            WORDS_API, json={"word": word, "meaning": meaning}, headers=headers or self.headers
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def listing(self, **params):
        response = self.client.get(WORDS_API, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def words_of(self, **params):
        return [item["word"] for item in self.listing(**params)["items"]]

    def add_plan_and_record(self, word_id):
        with self.db() as db:
            user_id = db.scalar(select(User.id))
            plan_item = PlanItem(
                user_id=user_id, day=1, word_id=word_id, assigned_type="new", position=0
            )
            db.add(plan_item)
            db.add(StudyRecord(user_id=user_id, word_id=word_id, wrong_count=3))
            db.flush()
            db.get(UserSetting, user_id).memorize_cursor_item_id = plan_item.id
            db.commit()


class AddWordTest(WordsTestCase):
    def test_add_returns_item(self):
        item = self.add("apple", "사과")
        self.assertEqual(item["word"], "apple")
        self.assertEqual(item["meaning"], "사과")
        self.assertTrue(item["created_at"].endswith("Z"))
        with self.db() as db:
            self.assertEqual(db.get(Word, item["id"]).word_key, "apple")

    def test_add_trims_and_normalizes_meanings(self):
        item = self.add("  Run ", " 달리다 / /운영하다/ ")
        self.assertEqual(item["word"], "Run")
        self.assertEqual(item["meaning"], "달리다/운영하다")

    def test_case_only_difference_is_duplicate(self):
        self.add("apple")
        response = self.client.post(
            WORDS_API, json={"word": "APPLE", "meaning": "x"}, headers=self.headers
        )
        self.assertEqual(response.status_code, 409)
        error = response.json()["error"]
        self.assertEqual(error["code"], "WORD_DUPLICATE")
        self.assertIn("apple", error["message"])
        self.assertIn("word", error["fields"])

    def test_invalid_input_returns_fields(self):
        cases = [
            ({"word": "", "meaning": "뜻"}, "word"),
            ({"word": "   ", "meaning": "뜻"}, "word"),
            ({"word": "apple", "meaning": ""}, "meaning"),
            ({"word": "apple", "meaning": " / / "}, "meaning"),
            ({"word": "x" * 101, "meaning": "뜻"}, "word"),
            ({"word": "apple", "meaning": "뜻" * 501}, "meaning"),
            ({"word": "a\u0000b", "meaning": "뜻"}, "word"),
            ({"word": "apple", "meaning": "한\n줄"}, "meaning"),
            ({"word": 123, "meaning": "뜻"}, "word"),
        ]
        for payload, field in cases:
            with self.subTest(field=field, payload=str(payload)[:40]):
                response = self.client.post(WORDS_API, json=payload, headers=self.headers)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["error"]["fields"])

    def test_length_boundaries_are_accepted(self):
        self.add("x" * 100, "뜻" * 500)

    def test_phrase_and_hyphen_words_are_accepted(self):
        self.add("look up", "찾아보다")
        self.add("-ing", "접미사")

    def test_concurrent_duplicate_returns_409(self):
        self.add("apple")
        real_find = word_repository.find_active_by_key
        calls = []

        def miss_first_check(db, user_id, word_key):
            calls.append(word_key)
            return None if len(calls) == 1 else real_find(db, user_id, word_key)

        with mock.patch.object(word_repository, "find_active_by_key", miss_first_check):
            response = self.client.post(
                WORDS_API, json={"word": "APPLE", "meaning": "x"}, headers=self.headers
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("apple", response.json()["error"]["message"])


class ReviveWordTest(WordsTestCase):
    def test_readding_deleted_word_keeps_id_and_record(self):
        item = self.add("apple", "사과")
        self.add_plan_and_record(item["id"])
        self.client.post(DELETE_API, json={"ids": [item["id"]]}, headers=self.headers)
        revived = self.add("APPLE", "애플")
        self.assertEqual(revived["id"], item["id"])
        self.assertEqual(revived["word"], "APPLE")
        self.assertEqual(revived["meaning"], "애플")
        self.assertEqual(revived["created_at"], item["created_at"])
        with self.db() as db:
            self.assertEqual(len(db.scalars(select(Word)).all()), 1)
            self.assertEqual(db.scalar(select(StudyRecord)).wrong_count, 3)

    def test_latest_deleted_row_is_revived_when_several_exist(self):
        first = self.add("apple")
        self.client.post(DELETE_API, json={"ids": [first["id"]]}, headers=self.headers)
        second = self.add("pear")
        self.client.patch(f"{WORDS_API}/{second['id']}", json={"word": "apple"}, headers=self.headers)
        self.client.post(DELETE_API, json={"ids": [second["id"]]}, headers=self.headers)
        self.assertEqual(self.add("apple")["id"], second["id"])


class ListWordsTest(WordsTestCase):
    def add_sample(self):
        self.add("cherry", "체리")
        self.add("Apple", "사과/애플")
        self.add("banana", "바나나")

    def test_default_sort_is_word_ascending_ignoring_case(self):
        self.add_sample()
        self.assertEqual(self.words_of(), ["Apple", "banana", "cherry"])

    def test_sort_options(self):
        self.add_sample()
        self.assertEqual(self.words_of(order="desc"), ["cherry", "banana", "Apple"])
        self.assertEqual(self.words_of(sort="created"), ["cherry", "Apple", "banana"])
        self.assertEqual(self.words_of(sort="created", order="desc"), ["banana", "Apple", "cherry"])
        self.assertEqual(self.words_of(sort="meaning"), ["banana", "Apple", "cherry"])

    def test_search_matches_word_or_meaning_ignoring_case(self):
        self.add_sample()
        self.assertEqual(self.words_of(q="APP"), ["Apple"])
        self.assertEqual(self.words_of(q="애플"), ["Apple"])
        self.assertEqual(self.words_of(q="  체리 "), ["cherry"])
        self.assertEqual(self.listing(q="없는말"), {"items": [], "total": 0})

    def test_search_treats_wildcards_as_plain_text(self):
        self.add("100%", "백퍼센트")
        self.add("a_b", "밑줄")
        self.add("plain", "보통")
        self.assertEqual(self.words_of(q="%"), ["100%"])
        self.assertEqual(self.words_of(q="_"), ["a_b"])

    def test_paging_returns_total_and_does_not_repeat(self):
        for index in range(5):
            self.add(f"word{index}", "같은 뜻")
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
        item = self.add("apple")
        self.client.post(DELETE_API, json={"ids": [item["id"]]}, headers=self.headers)
        self.assertEqual(self.listing()["total"], 0)
        self.assertEqual(self.listing(q="apple")["total"], 0)


class UpdateWordTest(WordsTestCase):
    def patch(self, word_id, **payload):
        return self.client.patch(f"{WORDS_API}/{word_id}", json=payload, headers=self.headers)

    def test_rename_keeps_id_record_and_plan(self):
        item = self.add("aple", "사과")
        self.add_plan_and_record(item["id"])
        response = self.patch(item["id"], word="apple")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], item["id"])
        self.assertEqual(response.json()["meaning"], "사과")
        with self.db() as db:
            self.assertEqual(db.get(Word, item["id"]).word_key, "apple")
            self.assertEqual(db.scalar(select(StudyRecord)).word_id, item["id"])
            self.assertEqual(db.scalar(select(PlanItem)).word_id, item["id"])

    def test_meaning_only_change(self):
        item = self.add("apple", "사과")
        response = self.patch(item["id"], meaning="애플 / 사과")
        self.assertEqual(response.json()["word"], "apple")
        self.assertEqual(response.json()["meaning"], "애플/사과")

    def test_own_case_change_is_allowed(self):
        item = self.add("apple")
        response = self.patch(item["id"], word="APPLE")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["word"], "APPLE")

    def test_rename_to_other_word_is_duplicate(self):
        self.add("apple")
        item = self.add("pear")
        response = self.patch(item["id"], word="Apple")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "WORD_DUPLICATE")
        with self.db() as db:
            self.assertEqual(db.get(Word, item["id"]).word, "pear")

    def test_rename_to_deleted_word_is_allowed(self):
        deleted = self.add("apple")
        self.client.post(DELETE_API, json={"ids": [deleted["id"]]}, headers=self.headers)
        item = self.add("pear")
        self.assertEqual(self.patch(item["id"], word="apple").status_code, 200)

    def test_empty_values_are_rejected(self):
        item = self.add("apple")
        self.assertEqual(self.patch(item["id"], word="  ").status_code, 400)
        self.assertEqual(self.patch(item["id"], meaning="/").status_code, 400)

    def test_missing_or_deleted_word_returns_404(self):
        item = self.add("apple")
        self.client.post(DELETE_API, json={"ids": [item["id"]]}, headers=self.headers)
        for word_id in (item["id"], 999999):
            response = self.patch(word_id, word="new")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    def test_out_of_range_id_returns_400(self):
        for word_id in (0, 2**31, 2**70):
            self.assertEqual(self.patch(word_id, word="new").status_code, 400, word_id)


class DeleteWordsTest(WordsTestCase):
    def delete(self, ids):
        return self.client.post(DELETE_API, json={"ids": ids}, headers=self.headers)

    def test_delete_is_soft_and_removes_plan_but_keeps_record(self):
        item = self.add("apple")
        self.add_plan_and_record(item["id"])
        response = self.delete([item["id"]])
        self.assertEqual(response.json(), {"deleted": 1})
        with self.db() as db:
            self.assertIsNotNone(db.get(Word, item["id"]).deleted_at)
            self.assertEqual(db.scalars(select(PlanItem)).all(), [])
            self.assertEqual(db.scalar(select(StudyRecord)).wrong_count, 3)
            # 가리키던 진도 항목이 사라지면 암기 커서도 비워진다 (데이터 모델 §3.4)
            self.assertIsNone(db.scalar(select(UserSetting)).memorize_cursor_item_id)

    def test_delete_several_counts_only_existing(self):
        first = self.add("apple")
        second = self.add("pear")
        self.add("keep")
        self.assertEqual(self.delete([first["id"], second["id"], 999999]).json(), {"deleted": 2})
        self.assertEqual(self.delete([first["id"]]).json(), {"deleted": 0})
        self.assertEqual(self.listing()["total"], 1)

    def test_invalid_id_lists_are_rejected(self):
        for ids in ([], [0], [2**31], ["x"], list(range(1, 1002))):
            with self.subTest(size=len(ids)):
                self.assertEqual(self.delete(ids).status_code, 400)


class WordPermissionTest(AuthTestCase):
    def test_anonymous_gets_401_everywhere(self):
        requests = [
            ("GET", WORDS_API),
            ("POST", WORDS_API),
            ("PATCH", f"{WORDS_API}/1"),
            ("POST", DELETE_API),
            ("POST", f"{WORDS_API}/import"),
            ("GET", f"{WORDS_API}/export"),
        ]
        payloads = {
            WORDS_API: {"word": "a", "meaning": "b"},
            f"{WORDS_API}/1": {"word": "a"},
            DELETE_API: {"ids": [1]},
        }
        for method, url in requests:
            with self.subTest(method=method, url=url):
                if url.endswith("/import"):
                    response = self.client.post(url, files={"file": ("w.csv", b"word,meaning\n")})
                elif method == "GET":
                    response = self.client.get(url)
                else:
                    response = self.client.request(method, url, json=payloads[url])
                self.assertEqual(response.status_code, 401, response.text)

    def test_unverified_member_can_read_but_not_write(self):
        headers = {"X-CSRF-Token": self.signup_and_login()}
        self.assertEqual(self.client.get(WORDS_API).status_code, 200)
        self.assertEqual(self.client.get(f"{WORDS_API}/export").status_code, 200)
        writes = [
            self.client.post(WORDS_API, json={"word": "a", "meaning": "b"}, headers=headers),
            self.client.patch(f"{WORDS_API}/1", json={"word": "a"}, headers=headers),
            self.client.post(DELETE_API, json={"ids": [1]}, headers=headers),
            self.client.post(
                f"{WORDS_API}/import", files={"file": ("w.csv", b"word,meaning\n")}, headers=headers
            ),
        ]
        for response in writes:
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["error"]["code"], "EMAIL_NOT_VERIFIED")

    def test_writes_require_csrf_token(self):
        self.verified_member()
        writes = [
            self.client.post(WORDS_API, json={"word": "a", "meaning": "b"}),
            self.client.patch(f"{WORDS_API}/1", json={"word": "a"}),
            self.client.post(DELETE_API, json={"ids": [1]}),
            self.client.post(f"{WORDS_API}/import", files={"file": ("w.csv", b"word,meaning\n")}),
        ]
        for response in writes:
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")


if __name__ == "__main__":
    unittest.main()

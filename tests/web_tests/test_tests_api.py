#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시험 시작, 정답 보호, 채점, 두 번 제출, 폐기, 기록 API 테스트 (FR-TEST-01~08)
# 파일 위치: tests/web_tests/test_tests_api.py

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from web_tests.support import AuthTestCase

from sqlalchemy import select, update

from web.db.tables import StudyRecord, TestAttempt, TestAttemptItem, TestSession, Word
from web.services import test_service

TESTS_API = "/api/v1/tests"
WORDS_API = "/api/v1/words"
HISTORY_API = "/api/v1/tests/history"
SAMPLE_WORDS = {"apple": "사과", "river": "강", "tree": "나무", "sea": "바다", "stone": "돌"}
SECRET_KEYS = {"answers", "correct_index", "word", "word_id", "correct_answer"}


class TestsTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.headers = self.verified_member()

    def add_words(self, words=None, email="learner@example.com"):
        self.insert_words(words or SAMPLE_WORDS, email=email)

    def start(self, test_format="multiple", test_direction="en_ko", count=5, **extra):
        return self.client.post(
            TESTS_API,
            json={"test_format": test_format, "test_direction": test_direction, "count": count, **extra},
            headers=self.headers,
        )

    def start_ok(self, *args, **kwargs):
        response = self.start(*args, **kwargs)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def submit(self, attempt_id, answers, client=None, headers=None):
        return (client or self.client).post(
            f"{TESTS_API}/{attempt_id}/submit",
            json={"answers": answers},
            headers=headers or self.headers,
        )

    def stored_items(self, attempt_id):
        with self.db() as db:
            return {
                item.id: item
                for item in db.scalars(
                    select(TestAttemptItem).where(TestAttemptItem.attempt_id == attempt_id)
                )
            }

    def right_answers(self, attempt):
        stored = self.stored_items(attempt["id"])
        answers = []
        for item in attempt["items"]:
            row = stored[item["id"]]
            value = row.correct_index if row.choices else json.loads(row.answers)[0]
            answers.append({"item_id": item["id"], "answer": value})
        return answers

    def wrong_answers(self, attempt):
        stored = self.stored_items(attempt["id"])
        answers = []
        for item in attempt["items"]:
            row = stored[item["id"]]
            value = (row.correct_index + 1) % 4 if row.choices else "틀린 답"
            answers.append({"item_id": item["id"], "answer": value})
        return answers

    def wrong_counts(self):
        with self.db() as db:
            return {
                word: count
                for word, count in db.execute(
                    select(Word.word, StudyRecord.wrong_count).join(
                        StudyRecord, StudyRecord.word_id == Word.id
                    )
                )
            }

    def expire(self, attempt_id):
        with self.db() as db:
            db.execute(
                update(TestAttempt)
                .where(TestAttempt.id == attempt_id)
                .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
            )
            db.commit()


class TestStartTest(TestsTestCase):
    def test_multiple_choice_has_four_choices_including_answer(self):
        self.add_words()
        attempt = self.start_ok()
        self.assertEqual(len(attempt["items"]), 5)
        self.assertEqual([item["position"] for item in attempt["items"]], [1, 2, 3, 4, 5])
        for item in attempt["items"]:
            self.assertEqual(len(item["choices"]), 4)
            self.assertEqual(item["direction"], "en_ko")
            self.assertIn(item["question"], SAMPLE_WORDS)
            self.assertIn(SAMPLE_WORDS[item["question"]], item["choices"])

    def test_subjective_has_no_choices(self):
        self.add_words()
        attempt = self.start_ok("subjective", "ko_en")
        for item in attempt["items"]:
            self.assertEqual(item["choices"], [])
            self.assertIn(item["question"], SAMPLE_WORDS.values())

    def test_both_direction_uses_only_real_directions(self):
        self.add_words()
        attempt = self.start_ok("subjective", "both")
        self.assertTrue({item["direction"] for item in attempt["items"]} <= {"en_ko", "ko_en"})
        self.assertEqual(attempt["test_direction"], "both")

    def test_count_limits_questions_and_word_count_caps_it(self):
        self.add_words()
        self.assertEqual(len(self.start_ok(count=2)["items"]), 2)
        self.assertEqual(len(self.start_ok(count=200)["items"]), 5)

    def test_invalid_input_is_rejected(self):
        self.add_words()
        for kwargs, field in (
            ({"test_format": "essay"}, "test_format"),
            ({"test_direction": "ko_ko"}, "test_direction"),
            ({"count": 0}, "count"),
            ({"count": 201}, "count"),
            ({"count": "5"}, "count"),
            ({"count": True}, "count"),
            ({"count": 1, "extra": 1}, "extra"),
        ):
            with self.subTest(kwargs=kwargs):
                response = self.start(**kwargs)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn(field, response.json()["error"]["fields"])

    def test_no_words_returns_422(self):
        response = self.start("subjective")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "TEST_NOT_POSSIBLE")

    def test_too_few_words_for_multiple_returns_422(self):
        self.add_words({"a1": "일", "a2": "이", "a3": "삼"})
        response = self.start("multiple")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "TEST_NOT_POSSIBLE")
        self.assertIn("4개", response.json()["error"]["message"])
        self.assertEqual(self.start("subjective").status_code, 201)

    def test_same_meaning_words_cannot_fill_choices_returns_422(self):
        # 단어는 충분해도 보기를 만들 다른 뜻이 부족하면 core가 거절한다 (D-21)
        self.add_words({"a1": "같음", "a2": "같음", "a3": "같음", "a4": "같음"})
        response = self.start("multiple", count=4)
        self.assertEqual(response.status_code, 422)
        with self.db() as db:
            self.assertEqual(db.scalars(select(TestAttempt)).all(), [])

    def test_deleted_word_is_not_asked(self):
        self.add_words()
        word_id = next(row["id"] for row in self.client.get(WORDS_API).json()["items"]
                       if row["word"] == "apple")
        self.delete_words([word_id])
        questions = {item["question"] for item in self.start_ok("subjective")["items"]}
        self.assertNotIn("apple", questions)

    def test_new_test_replaces_open_test(self):
        self.add_words()
        first = self.start_ok()
        second = self.start_ok()
        self.assertEqual(self.client.get(f"{TESTS_API}/{first['id']}").json()["error"]["code"], "TEST_EXPIRED")
        self.assertEqual(self.client.get(f"{TESTS_API}/{second['id']}").status_code, 200)
        response = self.submit(first["id"], [])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "TEST_EXPIRED")


class AnswerProtectionTest(TestsTestCase):
    def assert_no_secret(self, attempt):
        for item in attempt["items"]:
            self.assertFalse(SECRET_KEYS & set(item), item)

    def test_start_and_get_hide_answers(self):
        self.add_words()
        for test_format in ("multiple", "subjective"):
            for direction in ("en_ko", "ko_en", "both"):
                with self.subTest(test_format=test_format, direction=direction):
                    attempt = self.start_ok(test_format, direction)
                    self.assert_no_secret(attempt)
                    fetched = self.client.get(f"{TESTS_API}/{attempt['id']}").json()
                    self.assert_no_secret(fetched)
                    self.assertEqual(fetched["items"], attempt["items"])

    def test_subjective_question_body_does_not_contain_answer(self):
        self.add_words({"apple": "사과"})
        response = self.start("subjective", "ko_en", count=1)
        self.assertNotIn("apple", response.text)


class SubmitTest(TestsTestCase):
    def test_all_right_answers_score_full(self):
        self.add_words()
        attempt = self.start_ok()
        response = self.submit(attempt["id"], self.right_answers(attempt))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["total"], body["score"], body["percent"]), (5, 5, 100))
        self.assertTrue(all(item["correct"] for item in body["items"]))
        self.assertEqual(self.wrong_counts(), {})

    def test_wrong_answers_record_wrong_count_and_date(self):
        self.add_words()
        attempt = self.start_ok(count=2)
        with mock.patch.object(test_service, "today_in_korea", return_value=date(2026, 11, 4)):
            body = self.submit(attempt["id"], self.wrong_answers(attempt)).json()
        self.assertEqual(body["score"], 0)
        self.assertEqual(sorted(self.wrong_counts().values()), [1, 1])
        with self.db() as db:
            self.assertEqual(db.scalars(select(StudyRecord)).first().last_wrong_date, date(2026, 11, 4))

    def test_wrong_count_accumulates_each_test(self):
        # 같은 날 여러 번 시험을 봐도 시험마다 쌓는다 (D-11)
        self.add_words()
        for _ in range(2):
            attempt = self.start_ok(count=5)
            self.assertEqual(self.submit(attempt["id"], self.wrong_answers(attempt)).status_code, 200)
        self.assertEqual(set(self.wrong_counts().values()), {2})

    def test_result_shows_answers_only_after_submit(self):
        self.add_words({"apple": "사과/능금"})
        attempt = self.start_ok("subjective", "en_ko", count=1)
        item = attempt["items"][0]
        entry = self.submit(attempt["id"], [{"item_id": item["id"], "answer": "틀림"}]).json()["items"][0]
        self.assertEqual(entry["correct_answer"], "사과 / 능금")
        self.assertEqual(entry["your_answer"], "틀림")
        self.assertFalse(entry["correct"])

    def test_multiple_result_shows_choice_text(self):
        self.add_words()
        attempt = self.start_ok(count=1)
        item = attempt["items"][0]
        stored = self.stored_items(attempt["id"])[item["id"]]
        entry = self.submit(
            attempt["id"], [{"item_id": item["id"], "answer": stored.correct_index}]
        ).json()["items"][0]
        self.assertEqual(entry["your_answer"], SAMPLE_WORDS[item["question"]])
        self.assertEqual(entry["correct_answer"], SAMPLE_WORDS[item["question"]])
        self.assertTrue(entry["correct"])

    def test_subjective_ignores_case_and_spaces(self):
        self.add_words({"Apple": "사과"})
        attempt = self.start_ok("subjective", "ko_en", count=1)
        item = attempt["items"][0]
        body = self.submit(attempt["id"], [{"item_id": item["id"], "answer": "  aPPLE "}]).json()
        self.assertEqual(body["score"], 1)

    def test_any_meaning_is_accepted(self):
        self.add_words({"run": "달리다/운영하다"})
        attempt = self.start_ok("subjective", "en_ko", count=1)
        item = attempt["items"][0]
        self.assertEqual(self.submit(attempt["id"], [{"item_id": item["id"], "answer": "운영하다"}]).json()["score"], 1)

    def test_same_meaning_word_is_accepted(self):
        # 같은 뜻 단어는 모두 정답이다 (D-21, FR-TEST-03)
        self.add_words({"big": "큰", "large": "큰"})
        attempt = self.start_ok("subjective", "ko_en", count=1)
        item = attempt["items"][0]
        stored = json.loads(self.stored_items(attempt["id"])[item["id"]].answers)
        self.assertEqual(sorted(stored), ["big", "large"])
        other = next(word for word in ("big", "large") if word != stored[0])
        self.assertEqual(self.submit(attempt["id"], [{"item_id": item["id"], "answer": other}]).json()["score"], 1)

    def test_unanswered_counts_as_wrong_but_not_in_wrong_count(self):
        self.add_words()
        attempt = self.start_ok("subjective", count=3)
        items = attempt["items"]
        body = self.submit(
            attempt["id"],
            [{"item_id": items[0]["id"], "answer": "틀림"}, {"item_id": items[1]["id"], "answer": "   "}],
        ).json()
        self.assertEqual((body["total"], body["score"]), (3, 0))
        self.assertEqual([entry["your_answer"] for entry in body["items"]], ["틀림", None, None])
        self.assertEqual(sorted(self.wrong_counts().values()), [1])

    def test_empty_submission_is_recorded(self):
        self.add_words()
        attempt = self.start_ok(count=2)
        body = self.submit(attempt["id"], []).json()
        self.assertEqual((body["total"], body["score"], body["percent"]), (2, 0, 0))
        self.assertEqual(self.wrong_counts(), {})

    def test_result_is_kept_after_settings_change(self):
        # 시작 시점의 형식과 방향으로 기록한다 (API §10-1)
        self.add_words()
        attempt = self.start_ok("subjective", "ko_en", count=1)
        self.client.put(
            "/api/v1/settings",
            json={"daily_new_count": 1, "daily_review_count": 0, "daily_wrong_count": 0,
                  "wrong_threshold": 1, "test_format": "multiple", "test_direction": "en_ko"},
            headers=self.headers,
        )
        self.submit(attempt["id"], [])
        entry = self.client.get(HISTORY_API).json()["items"][0]
        self.assertEqual((entry["test_format"], entry["test_direction"]), ("subjective", "ko_en"))

    def test_word_deleted_during_test_still_grades(self):
        self.add_words()
        attempt = self.start_ok(count=5)
        word_ids = [row["id"] for row in self.client.get(WORDS_API).json()["items"]]
        self.delete_words(word_ids)
        response = self.submit(attempt["id"], self.right_answers(attempt))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["score"], 5)

    def test_invalid_answers_change_nothing(self):
        self.add_words()
        attempt = self.start_ok(count=2)
        first_id = attempt["items"][0]["id"]
        for answers in (
            [{"item_id": first_id, "answer": 4}],
            [{"item_id": first_id, "answer": -1}],
            [{"item_id": first_id, "answer": "1"}],
            [{"item_id": first_id, "answer": True}],
            [{"item_id": first_id, "answer": None}],
            [{"item_id": 999999, "answer": 0}],
            [{"item_id": first_id, "answer": 0}, {"item_id": first_id, "answer": 1}],
            [{"item_id": first_id, "answer": 0, "correct": True}],
        ):
            with self.subTest(answers=answers):
                self.assertEqual(self.submit(attempt["id"], answers).status_code, 400)
        self.assertEqual(self.client.get(f"{TESTS_API}/{attempt['id']}").status_code, 200)
        self.assertEqual(self.client.get(HISTORY_API).json()["total_count"], 0)

    def test_subjective_rejects_number_and_long_answer(self):
        self.add_words()
        attempt = self.start_ok("subjective", count=1)
        item_id = attempt["items"][0]["id"]
        self.assertEqual(self.submit(attempt["id"], [{"item_id": item_id, "answer": 1}]).status_code, 400)
        self.assertEqual(self.submit(attempt["id"], [{"item_id": item_id, "answer": "x" * 501}]).status_code, 400)

    def test_answer_item_of_other_test_is_rejected(self):
        self.add_words()
        first = self.start_ok(count=1)
        second = self.start_ok(count=1)
        response = self.submit(second["id"], [{"item_id": first["items"][0]["id"], "answer": 0}])
        self.assertEqual(response.status_code, 400)


class SubmitOnceTest(TestsTestCase):
    def test_second_submit_is_rejected_and_counts_once(self):
        self.add_words()
        attempt = self.start_ok()
        answers = self.wrong_answers(attempt)
        self.assertEqual(self.submit(attempt["id"], answers).status_code, 200)
        response = self.submit(attempt["id"], answers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "TEST_ALREADY_SUBMITTED")
        self.assertEqual(set(self.wrong_counts().values()), {1})
        self.assertEqual(self.client.get(HISTORY_API).json()["total_count"], 1)

    def test_get_after_submit_returns_409(self):
        self.add_words()
        attempt = self.start_ok()
        self.submit(attempt["id"], [])
        response = self.client.get(f"{TESTS_API}/{attempt['id']}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "TEST_ALREADY_SUBMITTED")

    def test_request_that_loses_the_race_changes_nothing(self):
        # 읽은 뒤 제출 처리 전에 다른 요청이 먼저 제출한 상황을 재현한다
        self.add_words()
        attempt = self.start_ok()
        real_mark = test_service.test_repository.mark_submitted

        def other_request_wins_first(db, user_id, attempt_id, now):
            with self.db() as other_db:
                other_db.execute(
                    update(TestAttempt).where(TestAttempt.id == attempt_id).values(status="submitted")
                )
                other_db.commit()
            return real_mark(db, user_id, attempt_id, now)

        with mock.patch.object(test_service.test_repository, "mark_submitted", other_request_wins_first):
            response = self.submit(attempt["id"], self.wrong_answers(attempt))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.wrong_counts(), {})
        with self.db() as db:
            self.assertEqual(db.scalars(select(TestSession)).all(), [])


class ExpiryTest(TestsTestCase):
    def test_new_test_expires_after_24_hours(self):
        self.add_words()
        attempt = self.start_ok()
        with self.db() as db:
            row = db.get(TestAttempt, attempt["id"])
            self.assertEqual(row.expires_at - row.created_at, timedelta(hours=24))

    def test_expired_test_cannot_be_read_or_submitted(self):
        self.add_words()
        attempt = self.start_ok()
        self.expire(attempt["id"])
        for response in (
            self.client.get(f"{TESTS_API}/{attempt['id']}"),
            self.submit(attempt["id"], self.wrong_answers(attempt)),
        ):
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"]["code"], "TEST_EXPIRED")
        self.assertEqual(self.wrong_counts(), {})


if __name__ == "__main__":
    unittest.main()

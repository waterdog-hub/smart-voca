#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 일차 생성, 암기, 진행률 API 테스트 (FR-PLAN-01~06, FR-MEM-01~03)
# 파일 위치: tests/web_tests/test_plans_api.py

import unittest
from datetime import date, datetime, timezone
from unittest import mock

from web_tests.support import AuthTestCase

from sqlalchemy import select

from web.db.tables import PlanItem, StudyRecord, User, UserSetting, Word
from web.services import plan_service

PLANS_API = "/api/v1/plans"
ITEMS_API = "/api/v1/plan-items"
PROGRESS_API = "/api/v1/progress"
SETTINGS_API = "/api/v1/settings"
WORDS_API = "/api/v1/words"
SMALL_DAY = {
    "daily_new_count": 3,
    "daily_review_count": 1,
    "daily_wrong_count": 2,
    "wrong_threshold": 2,
    "test_format": "multiple",
    "test_direction": "en_ko",
}


class PlansTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.headers = self.verified_member()

    def add_words(self, *names, client=None, headers=None):
        for name in names:
            response = (client or self.client).post(
                WORDS_API,
                json={"word": name, "meaning": f"{name} 뜻"},
                headers=headers or self.headers,
            )
            self.assertEqual(response.status_code, 201, response.text)

    def use_small_day(self, **overrides):
        response = self.client.put(
            SETTINGS_API, json={**SMALL_DAY, **overrides}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)

    def create(self, client=None, headers=None):
        return (client or self.client).post(PLANS_API, headers=headers or self.headers)

    def create_ok(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def patch(self, item_id, **body):
        return self.client.patch(f"{ITEMS_API}/{item_id}", json=body, headers=self.headers)

    def finish_day(self, plan):
        for item in plan["items"]:
            self.assertEqual(self.patch(item["id"], done=True).status_code, 200)

    def day_words(self, plan, assigned_type):
        return [item["word"] for item in plan["items"] if item["assigned_type"] == assigned_type]

    def set_wrong_count(self, word, wrong_count):
        with self.db() as db:
            row = db.scalar(select(Word).where(Word.word == word))
            record = db.get(StudyRecord, (row.user_id, row.id))
            if record is None:
                record = StudyRecord(user_id=row.user_id, word_id=row.id)
                db.add(record)
            record.wrong_count = wrong_count
            db.commit()

    def record_of(self, word):
        with self.db() as db:
            row = db.scalar(select(Word).where(Word.word == word))
            return db.get(StudyRecord, (row.user_id, row.id))

    def current_day(self):
        with self.db() as db:
            return db.scalar(select(UserSetting.current_day))

    def assert_not_ready(self, response, reason):
        self.assertEqual(response.status_code, 409, response.text)
        error = response.json()["error"]
        self.assertEqual(error["code"], "PLAN_NOT_READY")
        self.assertEqual(error["reason"], reason)
        self.assertTrue(error["message"])


class PlanCreationRulesTest(PlansTestCase):
    """기존 test_day_planner의 규칙을 API로 재현한다 (구현 계획 §5)."""

    def test_first_day_has_only_new_words_in_wordbook_order(self):
        self.add_words("delta", "alpha", "charlie", "bravo")
        self.use_small_day()
        plan = self.create_ok()
        self.assertEqual(plan["day"], 1)
        self.assertEqual([item["word"] for item in plan["items"]], ["delta", "alpha", "charlie"])
        self.assertEqual({item["assigned_type"] for item in plan["items"]}, {"new"})
        self.assertEqual([item["position"] for item in plan["items"]], [1, 2, 3])
        self.assertFalse(any(item["done"] for item in plan["items"]))

    def test_item_has_word_and_meaning(self):
        self.add_words("apple")
        item = self.create_ok()["items"][0]
        self.assertEqual((item["word"], item["meaning"], item["day"]), ("apple", "apple 뜻", 1))

    def test_second_day_adds_review_word_from_previous_day(self):
        self.add_words("a1", "a2", "a3", "a4", "a5", "a6")
        self.use_small_day()
        first = self.create_ok()
        self.finish_day(first)
        second = self.create_ok()
        self.assertEqual(second["day"], 2)
        self.assertEqual(self.day_words(second, "new"), ["a4", "a5", "a6"])
        review = self.day_words(second, "review")
        self.assertEqual(len(review), 1)
        self.assertIn(review[0], ["a1", "a2", "a3"])

    def test_wrong_words_need_threshold_and_sorted_by_count(self):
        self.add_words("a1", "a2", "a3", "a4", "a5", "a6", "a7")
        self.use_small_day(daily_review_count=0)
        self.finish_day(self.create_ok())
        self.set_wrong_count("a1", 1)
        self.set_wrong_count("a2", 2)
        self.set_wrong_count("a3", 5)
        second = self.create_ok()
        self.assertEqual(self.day_words(second, "wrong"), ["a3", "a2"])

    def test_same_word_is_not_assigned_twice_in_a_day(self):
        self.add_words("a1", "a2", "a3", "a4")
        self.use_small_day(daily_new_count=1, daily_review_count=3, daily_wrong_count=3)
        self.finish_day(self.create_ok())
        self.set_wrong_count("a1", 9)
        second = self.create_ok()
        words = [item["word"] for item in second["items"]]
        self.assertEqual(len(words), len(set(words)))

    def test_after_all_memorized_short_wrong_slots_are_filled_with_review(self):
        self.add_words("a1", "a2", "a3")
        self.use_small_day()
        self.finish_day(self.create_ok())
        self.set_wrong_count("a1", 3)
        second = self.create_ok()
        self.assertEqual(self.day_words(second, "new"), [])
        self.assertEqual(self.day_words(second, "wrong"), ["a1"])
        # 복습 1칸과 오답의 빈 1칸을 복습으로 채운다
        self.assertEqual(len(self.day_words(second, "review")), 2)

    def test_settings_change_applies_only_to_next_day(self):
        self.add_words("a1", "a2", "a3", "a4", "a5", "a6")
        self.use_small_day()
        first = self.create_ok()
        self.use_small_day(daily_new_count=1, daily_review_count=0)
        self.assertEqual(len(self.client.get(f"{PLANS_API}/1").json()["items"]), 3)
        self.finish_day(first)
        self.assertEqual(len(self.create_ok()["items"]), 1)

    def test_deleted_word_is_not_assigned(self):
        self.add_words("a1", "a2")
        word_id = self.client.get(WORDS_API).json()["items"][0]["id"]
        self.client.post(f"{WORDS_API}/delete", json={"ids": [word_id]}, headers=self.headers)
        self.assertEqual([item["word"] for item in self.create_ok()["items"]], ["a2"])

    def test_current_day_matches_created_days(self):
        # 저장값 current_day가 실제 진도와 어긋나지 않는지 확인한다 (D-W10)
        self.add_words("a1", "a2", "a3", "a4")
        self.use_small_day(daily_new_count=2)
        self.assertEqual(self.current_day(), 0)
        self.finish_day(self.create_ok())
        self.create_ok()
        self.assertEqual(self.current_day(), 2)
        days = [row["day"] for row in self.client.get(PLANS_API).json()["items"]]
        self.assertEqual(max(days), self.current_day())


class PlanNotReadyTest(PlansTestCase):
    def test_no_words(self):
        self.assert_not_ready(self.create(), "NO_WORDS")
        self.assertEqual(self.current_day(), 0)

    def test_current_day_incomplete(self):
        self.add_words("a1", "a2")
        self.create_ok()
        self.assert_not_ready(self.create(), "CURRENT_DAY_INCOMPLETE")
        self.assertEqual(self.current_day(), 1)

    def test_nothing_left_to_assign(self):
        self.add_words("a1")
        self.use_small_day(daily_review_count=0, daily_wrong_count=0)
        self.finish_day(self.create_ok())
        self.assert_not_ready(self.create(), "WRONG_THRESHOLD_NOT_MET")
        self.assertEqual(self.current_day(), 1)

    def test_day_emptied_by_word_deletion_does_not_block_next_day(self):
        # 현재 일차가 단어 삭제로 비어도 잠기지 않는다 (D-18)
        self.add_words("a1", "a2", "a3")
        self.use_small_day(daily_new_count=1)
        word_id = self.create_ok()["items"][0]
        ids = [row["id"] for row in self.client.get(WORDS_API).json()["items"]
               if row["word"] == word_id["word"]]
        self.client.post(f"{WORDS_API}/delete", json={"ids": ids}, headers=self.headers)
        self.assertEqual(self.create_ok()["day"], 2)


class PlanConcurrencyTest(PlansTestCase):
    def test_request_that_loses_the_race_changes_nothing(self):
        # 진도를 계산하는 사이에 다른 요청이 먼저 일차를 만든 상황을 재현한다
        self.add_words("a1", "a2", "a3", "a4", "a5", "a6")
        self.use_small_day()
        real_planner = plan_service.DayPlanner

        def plan_after_other_request_wins(*args, **kwargs):
            with self.db() as other_db:
                other_db.scalar(select(UserSetting)).current_day = 1
                other_db.commit()
            return real_planner().create_next_day_plan(*args, **kwargs)

        with mock.patch.object(plan_service, "DayPlanner") as planner:
            planner.return_value.create_next_day_plan.side_effect = plan_after_other_request_wins
            response = self.create()
        self.assert_not_ready(response, "CURRENT_DAY_INCOMPLETE")
        self.assertEqual(self.current_day(), 1)
        with self.db() as db:
            self.assertEqual(db.scalars(select(PlanItem)).all(), [])

    def test_duplicate_item_rolls_back_day_change(self):
        # 유일 제약이 두 번째 방어선이다. 어긋나면 일차도 올리지 않는다
        self.add_words("a1", "a2")
        with self.db() as db:
            user_id = db.scalar(select(User.id))
            word = db.scalar(select(Word).where(Word.word == "a1"))
            db.add(PlanItem(user_id=user_id, day=1, word_id=word.id, assigned_type="new",
                            position=1, done=True))
            db.commit()
        self.assert_not_ready(self.create(), "CURRENT_DAY_INCOMPLETE")
        self.assertEqual(self.current_day(), 0)


class PlanReadTest(PlansTestCase):
    def test_list_summarizes_days(self):
        self.assertEqual(self.client.get(PLANS_API).json(), {"current_day": 0, "items": []})
        self.add_words("a1", "a2", "a3", "a4")
        self.use_small_day(daily_new_count=2, daily_review_count=0)
        first = self.create_ok()
        self.patch(first["items"][0]["id"], done=True)
        body = self.client.get(PLANS_API).json()
        self.assertEqual(body["current_day"], 1)
        self.assertEqual(body["items"], [{"day": 1, "total": 2, "done": 1}])

    def test_get_day_marks_current_and_past(self):
        self.add_words("a1", "a2")
        self.use_small_day(daily_new_count=1)
        self.finish_day(self.create_ok())
        self.create_ok()
        self.assertFalse(self.client.get(f"{PLANS_API}/1").json()["is_current"])
        self.assertTrue(self.client.get(f"{PLANS_API}/2").json()["is_current"])

    def test_missing_day_returns_404(self):
        self.assertEqual(self.client.get(f"{PLANS_API}/1").status_code, 404)
        self.assertEqual(self.client.get(f"{PLANS_API}/0").status_code, 400)

    def test_renamed_word_shows_new_name_in_plan(self):
        self.add_words("apple")
        plan = self.create_ok()
        word_id = self.client.get(WORDS_API).json()["items"][0]["id"]
        self.client.patch(f"{WORDS_API}/{word_id}", json={"word": "APPLE"}, headers=self.headers)
        item = self.client.get(f"{PLANS_API}/1").json()["items"][0]
        self.assertEqual((item["id"], item["word"]), (plan["items"][0]["id"], "APPLE"))


class MemorizeTest(PlansTestCase):
    def setUp(self):
        super().setUp()
        self.add_words("a1", "a2", "a3")
        self.plan = self.create_ok()
        self.first_id = self.plan["items"][0]["id"]

    def test_done_records_memorization(self):
        with mock.patch.object(plan_service, "today_in_korea", return_value=date(2026, 11, 4)):
            response = self.patch(self.first_id, done=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["done"])
        record = self.record_of("a1")
        self.assertEqual(record.memorized_count, 1)
        self.assertEqual(record.first_memorized_day, 1)
        self.assertEqual(record.last_memorized_date, date(2026, 11, 4))

    def test_done_twice_counts_once(self):
        self.assertEqual(self.patch(self.first_id, done=True).status_code, 200)
        second = self.patch(self.first_id, done=True)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["done"])
        self.assertEqual(self.record_of("a1").memorized_count, 1)

    def test_memorized_count_accumulates_across_days(self):
        self.finish_day(self.plan)
        self.use_small_day(daily_new_count=1, daily_review_count=3, daily_wrong_count=0)
        for item in self.create_ok()["items"]:
            self.assertEqual(self.patch(item["id"], done=True).status_code, 200)
        reviewed = self.client.get(f"{PLANS_API}/2").json()["items"][0]["word"]
        record = self.record_of(reviewed)
        self.assertEqual(record.memorized_count, 2)
        self.assertEqual(record.first_memorized_day, 1)

    def test_later_moves_card_to_end_without_record(self):
        response = self.patch(self.first_id, later=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["done"])
        words = [item["word"] for item in self.client.get(f"{PLANS_API}/1").json()["items"]]
        self.assertEqual(words, ["a2", "a3", "a1"])
        self.assertIsNone(self.record_of("a1"))

    def test_order_survives_reload_so_next_card_is_restored(self):
        # 위치 저장 없이 순서와 완료 여부만으로 이어 간다 (FR-MEM-03, D-10)
        self.patch(self.first_id, later=True)
        items = self.client.get(f"{PLANS_API}/1").json()["items"]
        self.patch(items[0]["id"], done=True)
        items = self.client.get(f"{PLANS_API}/1").json()["items"]
        self.assertEqual([i["word"] for i in items if not i["done"]][0], "a3")

    def test_later_on_finished_card_changes_nothing(self):
        self.patch(self.first_id, done=True)
        response = self.patch(self.first_id, later=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["position"], 1)
        self.assertTrue(response.json()["done"])

    def test_past_day_card_cannot_change(self):
        self.finish_day(self.plan)
        self.use_small_day(daily_new_count=1)
        self.create_ok()
        before = self.record_of("a1").memorized_count
        for body in ({"done": True}, {"later": True}):
            with self.subTest(body=body):
                response = self.patch(self.first_id, **body)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["error"]["code"], "PLAN_ITEM_NOT_CURRENT")
        self.assertEqual(self.record_of("a1").memorized_count, before)
        self.assertEqual(self.client.get(f"{PLANS_API}/1").json()["items"][0]["position"], 1)

    def test_invalid_bodies_are_rejected(self):
        for body in ({}, {"done": False}, {"later": False}, {"done": True, "later": True},
                     {"done": 1}, {"done": True, "position": 9}):
            with self.subTest(body=body):
                response = self.client.patch(
                    f"{ITEMS_API}/{self.first_id}", json=body, headers=self.headers
                )
                self.assertEqual(response.status_code, 400, response.text)
        self.assertIsNone(self.record_of("a1"))

    def test_missing_item_returns_404(self):
        self.assertEqual(self.patch(999999, done=True).status_code, 404)

    def test_deleted_word_card_returns_404_and_keeps_record(self):
        self.patch(self.first_id, done=True)
        word_id = next(row["id"] for row in self.client.get(WORDS_API).json()["items"]
                       if row["word"] == "a1")
        self.client.post(f"{WORDS_API}/delete", json={"ids": [word_id]}, headers=self.headers)
        self.assertEqual(self.patch(self.first_id, done=True).status_code, 404)
        self.assertEqual(self.record_of("a1").memorized_count, 1)


class TodayTest(unittest.TestCase):
    def test_korea_date_is_used_near_midnight(self):
        # UTC 11월 3일 16시는 한국 11월 4일 새벽 1시다. 서버 위치와 상관없이 같아야 한다
        with mock.patch.object(plan_service, "datetime") as fake_datetime:
            fake_datetime.now.side_effect = lambda tz: datetime(
                2026, 11, 3, 16, tzinfo=timezone.utc
            ).astimezone(tz)
            self.assertEqual(plan_service.today_in_korea(), date(2026, 11, 4))


class ProgressTest(PlansTestCase):
    def progress(self):
        response = self.client.get(PROGRESS_API)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_new_member(self):
        self.assertEqual(
            self.progress(),
            {"total_words": 0, "memorized_words": 0, "current_day": 0, "day_total": 0, "day_done": 0},
        )

    def test_counts_follow_memorization(self):
        self.add_words("a1", "a2", "a3", "a4")
        self.use_small_day(daily_new_count=2)
        plan = self.create_ok()
        self.patch(plan["items"][0]["id"], done=True)
        self.assertEqual(
            self.progress(),
            {"total_words": 4, "memorized_words": 1, "current_day": 1, "day_total": 2, "day_done": 1},
        )

    def test_deleted_word_is_not_counted(self):
        self.add_words("a1", "a2")
        plan = self.create_ok()
        self.patch(plan["items"][0]["id"], done=True)
        word_id = next(row["id"] for row in self.client.get(WORDS_API).json()["items"]
                       if row["word"] == plan["items"][0]["word"])
        self.client.post(f"{WORDS_API}/delete", json={"ids": [word_id]}, headers=self.headers)
        progress = self.progress()
        self.assertEqual((progress["total_words"], progress["memorized_words"]), (1, 0))


class PlanPermissionTest(PlansTestCase):
    def test_reads_require_login(self):
        anonymous = self.make_auth_client(ip="anonymous")
        for path in (PLANS_API, f"{PLANS_API}/1", PROGRESS_API):
            with self.subTest(path=path):
                self.assertEqual(anonymous.get(path).status_code, 401)

    def test_writes_require_csrf_token(self):
        self.add_words("a1")
        item_id = self.create_ok()["items"][0]["id"]
        self.assertEqual(self.client.post(PLANS_API).status_code, 403)
        response = self.client.patch(f"{ITEMS_API}/{item_id}", json={"done": True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")

    def test_unverified_member_can_read_but_not_write(self):
        client = self.make_auth_client(ip="unverified")
        token = self.signup_and_login("unverified@example.com", client=client)
        headers = {"X-CSRF-Token": token}
        self.assertEqual(client.get(PROGRESS_API).status_code, 200)
        response = client.post(PLANS_API, headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "EMAIL_NOT_VERIFIED")

    def test_other_member_item_is_hidden(self):
        self.add_words("a1")
        plan = self.create_ok()
        other = self.make_auth_client(ip="other")
        other_headers = self.verified_member("other@example.com", client=other)
        self.assertEqual(other.get(f"{PLANS_API}/1").status_code, 404)
        response = other.patch(
            f"{ITEMS_API}/{plan['items'][0]['id']}", json={"done": True}, headers=other_headers
        )
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(self.record_of("a1"))
        self.assertEqual(other.get(PROGRESS_API).json()["current_day"], 0)

    def test_members_have_separate_days(self):
        self.add_words("a1")
        self.create_ok()
        other = self.make_auth_client(ip="other")
        other_headers = self.verified_member("other@example.com", client=other)
        self.add_words("own", client=other, headers=other_headers)
        created = self.create(client=other, headers=other_headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["day"], 1)
        self.assertEqual([i["word"] for i in created.json()["items"]], ["own"])


if __name__ == "__main__":
    unittest.main()

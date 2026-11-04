#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 설정 API와 화면 테스트 (FR-SET-01~03, D-23)
# 파일 위치: tests/web_tests/test_settings_api.py

import unittest

from web_tests.support import AuthTestCase

from sqlalchemy import select

from web.db.tables import PlanItem, User, UserSetting, Word

SETTINGS_API = "/api/v1/settings"
VALID_SETTINGS = {
    "daily_new_count": 10,
    "daily_review_count": 3,
    "daily_wrong_count": 2,
    "wrong_threshold": 4,
    "test_format": "subjective",
    "test_direction": "both",
}
DEFAULT_SETTINGS = {
    "daily_new_count": 20,
    "daily_review_count": 5,
    "daily_wrong_count": 5,
    "wrong_threshold": 3,
    "test_format": "multiple",
    "test_direction": "en_ko",
}


class SettingsTestCase(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.headers = self.verified_member()

    def put(self, client=None, headers=None, **overrides):
        return (client or self.client).put(
            SETTINGS_API,
            json={**VALID_SETTINGS, **overrides},
            headers=self.headers if headers is None else headers,
        )

    def assert_rejected_field(self, response, field_name):
        self.assertEqual(response.status_code, 400, response.text)
        error = response.json()["error"]
        self.assertEqual(error["code"], "VALIDATION_FAILED")
        self.assertIn(field_name, error["fields"])

    def assert_settings_unchanged(self):
        self.assertEqual(self.client.get(SETTINGS_API).json(), DEFAULT_SETTINGS)


class SettingsReadWriteTest(SettingsTestCase):
    def test_new_member_reads_defaults(self):
        response = self.client.get(SETTINGS_API)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), DEFAULT_SETTINGS)

    def test_save_returns_and_keeps_values(self):
        response = self.put()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), VALID_SETTINGS)
        self.assertEqual(self.client.get(SETTINGS_API).json(), VALID_SETTINGS)

    def test_every_allowed_choice_is_saved(self):
        for test_format in ("multiple", "subjective"):
            for test_direction in ("en_ko", "ko_en", "both"):
                with self.subTest(test_format=test_format, test_direction=test_direction):
                    response = self.put(test_format=test_format, test_direction=test_direction)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["test_format"], test_format)
                    self.assertEqual(response.json()["test_direction"], test_direction)

    def test_members_have_separate_settings(self):
        other_client = self.make_auth_client(ip="other-member")
        other_headers = self.verified_member("other@example.com", client=other_client)
        self.assertEqual(self.put().status_code, 200)
        self.assertEqual(other_client.get(SETTINGS_API).json(), DEFAULT_SETTINGS)
        response = self.put(client=other_client, headers=other_headers, daily_new_count=77)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(SETTINGS_API).json(), VALID_SETTINGS)
        self.assertEqual(other_client.get(SETTINGS_API).json()["daily_new_count"], 77)


class SettingsValidationTest(SettingsTestCase):
    def test_lowest_allowed_values_are_saved(self):
        # 복습과 오답 0은 신규 단어만 외우는 정상 사용이다
        response = self.put(
            daily_new_count=1, daily_review_count=0, daily_wrong_count=0, wrong_threshold=1
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_highest_allowed_values_are_saved(self):
        response = self.put(
            daily_new_count=9999,
            daily_review_count=9999,
            daily_wrong_count=9999,
            wrong_threshold=9999,
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_values_below_minimum_are_rejected(self):
        for field_name, value in (
            ("daily_new_count", 0),
            ("daily_review_count", -1),
            ("daily_wrong_count", -1),
            ("wrong_threshold", 0),
        ):
            with self.subTest(field_name=field_name):
                self.assert_rejected_field(self.put(**{field_name: value}), field_name)
        self.assert_settings_unchanged()

    def test_error_message_states_the_allowed_range(self):
        fields = self.put(daily_new_count=0).json()["error"]["fields"]
        self.assertEqual(fields["daily_new_count"], "1 이상 9999 이하로 입력해 주세요.")

    def test_values_above_maximum_are_rejected(self):
        # DB 정수 한도를 넘는 값도 드라이버 오류가 아니라 입력 오류로 끝난다
        for value in (10000, 2_147_483_648, 10**30):
            with self.subTest(value=value):
                self.assert_rejected_field(self.put(daily_new_count=value), "daily_new_count")
        self.assert_settings_unchanged()

    def test_non_integer_numbers_are_rejected(self):
        for value in ("5", True, 1.5, None):
            with self.subTest(value=value):
                self.assert_rejected_field(self.put(daily_new_count=value), "daily_new_count")
        self.assert_settings_unchanged()

    def test_unknown_choices_are_rejected(self):
        self.assert_rejected_field(self.put(test_format="essay"), "test_format")
        self.assert_rejected_field(self.put(test_direction="ko_ko"), "test_direction")
        self.assert_rejected_field(self.put(test_format="x" * 21), "test_format")
        self.assert_settings_unchanged()

    def test_every_invalid_field_is_reported_together(self):
        response = self.put(daily_new_count=0, wrong_threshold=0, test_format="essay")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            set(response.json()["error"]["fields"]),
            {"daily_new_count", "wrong_threshold", "test_format"},
        )

    def test_missing_field_is_rejected(self):
        payload = {key: value for key, value in VALID_SETTINGS.items() if key != "wrong_threshold"}
        response = self.client.put(SETTINGS_API, json=payload, headers=self.headers)
        self.assert_rejected_field(response, "wrong_threshold")
        self.assert_settings_unchanged()


class SettingsProtectedColumnsTest(SettingsTestCase):
    def set_progress(self):
        """현재 일차와 카드 위치가 있는 상태를 만들고 카드 번호를 돌려준다."""
        with self.db() as db:
            user_id = db.scalar(select(User.id))
            word = Word(user_id=user_id, word="apple", word_key="apple", meaning="사과")
            db.add(word)
            db.flush()
            item = PlanItem(
                user_id=user_id, day=4, word_id=word.id, assigned_type="new", position=0
            )
            db.add(item)
            db.flush()
            setting = db.get(UserSetting, user_id)
            setting.current_day = 4
            setting.memorize_cursor_item_id = item.id
            db.commit()
            return item.id

    def progress(self):
        with self.db() as db:
            setting = db.scalar(select(UserSetting))
            return setting.current_day, setting.memorize_cursor_item_id

    def test_sending_progress_columns_is_rejected(self):
        item_id = self.set_progress()
        for field_name, value in (("current_day", 99), ("memorize_cursor_item_id", None)):
            with self.subTest(field_name=field_name):
                self.assert_rejected_field(self.put(**{field_name: value}), field_name)
                self.assertEqual(self.progress(), (4, item_id))

    def test_saving_keeps_progress_columns(self):
        item_id = self.set_progress()
        self.assertEqual(self.put().status_code, 200)
        self.assertEqual(self.progress(), (4, item_id))

    def test_saving_does_not_overwrite_day_raised_after_loading(self):
        # 설정 저장 도중 진도 생성이 일차를 올려도 예전 값으로 되돌리지 않는다 (D-W10)
        self.set_progress()
        with self.db() as other_db:
            from web.schemas.settings import SettingsData
            from web.services.setting_service import SettingService

            service = SettingService(other_db, other_db.scalar(select(User.id)))
            service.get()
            with self.db() as plan_db:
                plan_db.scalar(select(UserSetting)).current_day = 5
                plan_db.commit()
            service.save(SettingsData(**VALID_SETTINGS))
        self.assertEqual(self.progress()[0], 5)

    def test_responses_do_not_include_progress_columns(self):
        self.set_progress()
        for response in (self.client.get(SETTINGS_API), self.put()):
            self.assertNotIn("current_day", response.json())
            self.assertNotIn("memorize_cursor_item_id", response.json())
            self.assertNotIn("user_id", response.json())


class SettingsPermissionTest(AuthTestCase):
    def test_reading_requires_login(self):
        response = self.client.get(SETTINGS_API)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_saving_requires_login(self):
        response = self.client.put(SETTINGS_API, json=VALID_SETTINGS)
        self.assertEqual(response.status_code, 401)

    def test_saving_requires_csrf_token(self):
        self.verified_member()
        response = self.client.put(SETTINGS_API, json=VALID_SETTINGS)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CSRF_INVALID")

    def test_unverified_member_can_read_but_not_save(self):
        csrf_token = self.signup_and_login()
        self.assertEqual(self.client.get(SETTINGS_API).status_code, 200)
        response = self.client.put(
            SETTINGS_API, json=VALID_SETTINGS, headers={"X-CSRF-Token": csrf_token}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "EMAIL_NOT_VERIFIED")
        self.assertEqual(self.client.get(SETTINGS_API).json(), DEFAULT_SETTINGS)


class SettingsPageTest(AuthTestCase):
    def test_page_requires_login(self):
        response = self.client.get("/settings", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?next=%2Fsettings")

    def test_page_has_labeled_fields_and_rules_without_inline_code(self):
        self.signup_and_login()
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        html = response.text
        for field_name in VALID_SETTINGS:
            self.assertIn(f'<label for="{field_name}">', html)
            self.assertIn(f'id="{field_name}-error"', html)
        self.assertIn('id="daily_new_count" name="daily_new_count"', html)
        self.assertIn('min="1" max="9999" aria-describedby="daily_new_count-help"', html)
        self.assertIn('min="0" max="9999" aria-describedby="daily_review_count-help"', html)
        self.assertIn('<option value="multiple">객관식</option>', html)
        self.assertIn('<option value="both">양방향</option>', html)
        self.assertIn('id="settings-save"', html)
        self.assertIn('id="settings-revert"', html)
        self.assertIn('src="/static/settings.js"', html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("onclick=", html)
        self.assertNotIn("style=", html)
        self.assertEqual(self.client.get("/static/settings.js").status_code, 200)

    def test_menu_links_to_settings_on_member_pages(self):
        self.signup_and_login()
        for path in ("/", "/words", "/memorize", "/plans", "/settings"):
            with self.subTest(path=path):
                self.assertIn('href="/settings"', self.client.get(path).text)
        self.assertIn(
            '<a href="/settings" aria-current="page">', self.client.get("/settings").text
        )

    def test_page_shows_banner_when_unverified(self):
        self.signup_and_login()
        self.assertIn('id="verify-banner"', self.client.get("/settings").text)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 테이블 제약, 탈퇴 시 삭제, UTC 시각 저장 테스트 (데이터 모델 v0.3)
# 파일 위치: tests/web_tests/test_tables.py

import unittest
from datetime import datetime, timedelta, timezone

from web_tests.support import WebTestCase

from alembic import command
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from web.db.base import make_engine, utc_now
from web.db.tables import (
    AuthSession,
    AuthToken,
    PlanItem,
    SocialAccount,
    StudyRecord,
    TestAttempt,
    TestAttemptItem,
    TestSession,
    User,
    UserSetting,
    Word,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
KST = timezone(timedelta(hours=9))


class TableTestCase(WebTestCase):
    def setUp(self):
        super().setUp()
        # create_all이 아니라 실제 마이그레이션으로 만든 스키마를 검사한다
        command.upgrade(self.make_alembic_config(), "head")
        engine = make_engine(self.database_url)
        self.addCleanup(engine.dispose)
        self.session = Session(engine)
        self.addCleanup(self.session.close)

    def add_user(self, email="user@example.com"):
        now = utc_now()
        user = User(email=email, display_name="회원", terms_agreed_at=now, privacy_agreed_at=now)
        self.session.add(user)
        self.session.commit()
        return user

    def add_word(self, user, text="apple"):
        word = Word(user_id=user.id, word=text, word_key=text.lower(), meaning="사과")
        self.session.add(word)
        self.session.commit()
        return word

    def assert_rejected(self, row):
        self.session.add(row)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def add_attempt(self, user):
        attempt = TestAttempt(
            user_id=user.id,
            test_format="multiple",
            test_direction="en_ko",
            expires_at=utc_now() + timedelta(hours=24),
        )
        self.session.add(attempt)
        self.session.commit()
        return attempt


class WordConstraintTest(TableTestCase):
    def test_same_word_key_is_rejected_for_same_user(self):
        user = self.add_user()
        self.add_word(user, "Apple")
        self.assert_rejected(Word(user_id=user.id, word="apple", word_key="apple", meaning="사과"))

    def test_word_can_be_added_again_after_soft_delete(self):
        user = self.add_user()
        word = self.add_word(user)
        word.deleted_at = utc_now()
        self.session.commit()
        self.add_word(user)
        count = len(self.session.scalars(select(Word).where(Word.user_id == user.id)).all())
        self.assertEqual(count, 2)

    def test_same_word_is_allowed_for_different_users(self):
        self.add_word(self.add_user("first@example.com"))
        self.add_word(self.add_user("second@example.com"))
        self.assertEqual(len(self.session.scalars(select(Word)).all()), 2)

    def test_word_row_cannot_be_hard_deleted_while_records_remain(self):
        user = self.add_user()
        word = self.add_word(user)
        self.session.add(StudyRecord(user_id=user.id, word_id=word.id))
        self.session.commit()
        self.session.delete(word)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()


class ForeignKeyTest(TableTestCase):
    def test_foreign_keys_are_enforced(self):
        self.assert_rejected(Word(user_id=999, word="ghost", word_key="ghost", meaning="유령"))


class CheckConstraintTest(TableTestCase):
    def test_email_must_be_unique(self):
        self.add_user()
        now = utc_now()
        self.assert_rejected(
            User(
                email="user@example.com",
                display_name="다른 회원",
                terms_agreed_at=now,
                privacy_agreed_at=now,
            )
        )

    def test_daily_new_count_must_be_at_least_one(self):
        user = self.add_user()
        self.assert_rejected(UserSetting(user_id=user.id, daily_new_count=0))

    def test_score_cannot_exceed_total(self):
        user = self.add_user()
        attempt = self.add_attempt(user)
        self.assert_rejected(
            TestSession(
                user_id=user.id,
                attempt_id=attempt.id,
                test_format="multiple",
                test_direction="en_ko",
                total=5,
                score=6,
            )
        )

    def test_attempt_can_be_submitted_only_once(self):
        user = self.add_user()
        attempt = self.add_attempt(user)
        self.session.add(
            TestSession(
                user_id=user.id,
                attempt_id=attempt.id,
                test_format="multiple",
                test_direction="en_ko",
                total=5,
                score=5,
            )
        )
        self.session.commit()
        self.assert_rejected(
            TestSession(
                user_id=user.id,
                attempt_id=attempt.id,
                test_format="multiple",
                test_direction="en_ko",
                total=5,
                score=5,
            )
        )

    def test_unknown_status_is_rejected(self):
        user = self.add_user()
        self.assert_rejected(
            TestAttempt(
                user_id=user.id,
                test_format="multiple",
                test_direction="en_ko",
                status="paused",
                expires_at=utc_now(),
            )
        )

    def make_auth_session(self, **values):
        return AuthSession(
            token_hash=HASH_A, csrf_token_hash=HASH_B, expires_at=utc_now(), **values
        )

    def test_auth_session_must_be_login_or_pending(self):
        user = self.add_user()
        self.assert_rejected(self.make_auth_session())
        self.assert_rejected(self.make_auth_session(user_id=user.id, pending_provider="kakao"))

    def test_auth_session_accepts_login_and_pending(self):
        user = self.add_user()
        self.session.add(self.make_auth_session(user_id=user.id))
        self.session.commit()
        pending = AuthSession(
            token_hash=HASH_B,
            csrf_token_hash=HASH_B,
            expires_at=utc_now(),
            pending_provider="kakao",
            pending_provider_user_id="12345",
        )
        self.session.add(pending)
        self.session.commit()
        self.assertEqual(len(self.session.scalars(select(AuthSession)).all()), 2)


class DefaultValueTest(TableTestCase):
    def test_settings_defaults_follow_design(self):
        user = self.add_user()
        setting = UserSetting(user_id=user.id)
        self.session.add(setting)
        self.session.commit()
        self.assertEqual(setting.daily_new_count, 20)
        self.assertEqual(setting.daily_review_count, 5)
        self.assertEqual(setting.daily_wrong_count, 5)
        self.assertEqual(setting.wrong_threshold, 3)
        self.assertEqual(setting.test_format, "multiple")
        self.assertEqual(setting.test_direction, "en_ko")
        self.assertEqual(setting.current_day, 0)


class CursorTest(TableTestCase):
    def test_cursor_is_cleared_when_plan_item_is_deleted(self):
        user = self.add_user()
        word = self.add_word(user)
        item = PlanItem(user_id=user.id, day=1, word_id=word.id, assigned_type="new", position=1)
        self.session.add(item)
        self.session.commit()
        setting = UserSetting(user_id=user.id, memorize_cursor_item_id=item.id)
        self.session.add(setting)
        self.session.commit()
        self.session.delete(item)
        self.session.commit()
        self.session.refresh(setting)
        self.assertIsNone(setting.memorize_cursor_item_id)


class UtcDateTimeTest(TableTestCase):
    def test_time_is_stored_and_returned_as_utc(self):
        user = self.add_user()
        user.email_verified_at = datetime(2026, 11, 4, 18, 0, tzinfo=KST)
        self.session.commit()
        self.session.expire_all()
        loaded = self.session.get(User, user.id).email_verified_at
        self.assertEqual(loaded, datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(loaded.utcoffset(), timedelta(0))

    def test_time_without_timezone_is_rejected(self):
        user = self.add_user()
        user.email_verified_at = datetime(2026, 11, 4, 9, 0)
        with self.assertRaises(StatementError):
            self.session.commit()
        self.session.rollback()


class AccountDeletionTest(TableTestCase):
    """탈퇴는 하드 삭제다. 회원 행을 지우면 그 회원의 데이터만 모두 사라져야 한다 (D-W12)."""

    def fill_user_data(self, user, token_hash):
        word = self.add_word(user)
        attempt = self.add_attempt(user)
        item = PlanItem(user_id=user.id, day=1, word_id=word.id, assigned_type="new", position=1)
        self.session.add(item)
        self.session.commit()
        self.session.add_all(
            [
                UserSetting(user_id=user.id, memorize_cursor_item_id=item.id),
                StudyRecord(user_id=user.id, word_id=word.id),
                SocialAccount(
                    user_id=user.id, provider="google", provider_user_id=f"google-{user.id}"
                ),
                AuthSession(
                    user_id=user.id,
                    token_hash=token_hash,
                    csrf_token_hash=HASH_B,
                    expires_at=utc_now(),
                ),
                AuthToken(
                    user_id=user.id,
                    purpose="verify_email",
                    token_hash=token_hash,
                    expires_at=utc_now(),
                ),
                TestAttemptItem(
                    attempt_id=attempt.id,
                    position=1,
                    word_id=word.id,
                    direction="en_ko",
                    question="apple",
                    answers='["사과"]',
                ),
                TestSession(
                    user_id=user.id,
                    attempt_id=attempt.id,
                    test_format="multiple",
                    test_direction="en_ko",
                    total=1,
                    score=1,
                ),
            ]
        )
        self.session.commit()

    def count_rows(self):
        owned_tables = (
            SocialAccount,
            Word,
            UserSetting,
            StudyRecord,
            PlanItem,
            TestSession,
            TestAttempt,
            TestAttemptItem,
            AuthSession,
            AuthToken,
        )
        return {
            table.__tablename__: len(self.session.scalars(select(table)).all())
            for table in owned_tables
        }

    def test_deleting_user_removes_only_that_users_data(self):
        leaving_user = self.add_user("leaving@example.com")
        staying_user = self.add_user("staying@example.com")
        self.fill_user_data(leaving_user, "c" * 64)
        self.fill_user_data(staying_user, "d" * 64)

        self.session.delete(leaving_user)
        self.session.commit()
        self.session.expire_all()

        self.assertEqual(set(self.count_rows().values()), {1})
        self.assertIsNotNone(self.session.get(User, staying_user.id))
        self.assertEqual(self.session.scalars(select(Word.user_id)).all(), [staying_user.id])

    def test_same_email_can_join_again_after_deletion(self):
        user = self.add_user("again@example.com")
        self.session.delete(user)
        self.session.commit()
        self.assertIsNotNone(self.add_user("again@example.com").id)


if __name__ == "__main__":
    unittest.main()

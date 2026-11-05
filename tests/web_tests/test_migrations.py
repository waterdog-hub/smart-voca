#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 마이그레이션 적용·되돌리기와 테이블 정의 일치 테스트
# 파일 위치: tests/web_tests/test_migrations.py

import unittest

from web_tests.support import WebTestCase

from alembic import command
from sqlalchemy import inspect

from web.db.base import make_engine

EXPECTED_TABLES = {
    "users",
    "social_accounts",
    "words",
    "settings",
    "study_records",
    "plan_items",
    "test_sessions",
    "test_attempts",
    "test_attempt_items",
    "auth_sessions",
    "auth_tokens",
    "login_attempts",
    "wordbooks",
    "wordbook_entries",
    "user_wordbooks",
}
VERSION_TABLE = "alembic_version"


class MigrationTest(WebTestCase):
    def read_tables(self):
        engine = make_engine(self.database_url)
        self.addCleanup(engine.dispose)
        try:
            return set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    def test_upgrade_creates_all_tables(self):
        command.upgrade(self.make_alembic_config(), "head")
        self.assertEqual(self.read_tables(), EXPECTED_TABLES | {VERSION_TABLE})

    def test_downgrade_removes_all_tables(self):
        config = self.make_alembic_config()
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        self.assertEqual(self.read_tables() - {VERSION_TABLE}, set())

    def test_upgrade_works_again_after_downgrade(self):
        config = self.make_alembic_config()
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        self.assertEqual(self.read_tables(), EXPECTED_TABLES | {VERSION_TABLE})

    def test_upgrade_from_first_migration_keeps_existing_words(self):
        # 단어장 추가는 새 테이블만 만든다. 기존 회원 단어를 건드리지 않는다 (D-WB10)
        config = self.make_alembic_config()
        command.upgrade(config, "0001")
        engine = make_engine(self.database_url)
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, display_name, terms_agreed_at, privacy_agreed_at, created_at)"
                " VALUES (1, 'a@example.com', '학습자', '2026-11-05', '2026-11-05', '2026-11-05')"
            )
            connection.exec_driver_sql(
                "INSERT INTO words (user_id, word, word_key, meaning, created_at, updated_at)"
                " VALUES (1, 'apple', 'apple', '사과', '2026-11-05', '2026-11-05')"
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = connection.exec_driver_sql("SELECT word FROM words").fetchall()
        self.assertEqual(rows, [("apple",)])

    def test_tables_match_latest_migration(self):
        # tables.py를 고치고 마이그레이션을 빠뜨리면 이 테스트가 실패한다
        config = self.make_alembic_config()
        command.upgrade(config, "head")
        command.check(config)


if __name__ == "__main__":
    unittest.main()

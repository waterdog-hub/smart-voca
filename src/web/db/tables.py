#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 웹 서비스 테이블 15개를 정의한다 (docs/web 데이터 모델 문서 기준)
# 파일 위치: src/web/db/tables.py

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from config import DEFAULT_SETTINGS
from web.db.base import Base, UtcDateTime, utc_now

SHA256_HEX_LENGTH = 64
TEST_FORMATS = ("multiple", "subjective")
TEST_DIRECTIONS = ("en_ko", "ko_en", "both")


def allowed_values_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({quoted_values})", name=name)


def user_id_column(*, index: bool = False, primary_key: bool = False) -> Mapped[int]:
    # 탈퇴는 회원 행을 지우는 하드 삭제이므로 회원 소유 데이터가 함께 지워지게 한다 (D-W12)
    return mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=index, primary_key=primary_key
    )


def default_setting_column(name: str) -> Mapped[int]:
    default_value = DEFAULT_SETTINGS[name]
    return mapped_column(Integer, default=default_value, server_default=text(str(default_value)))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 이메일 최대 길이 254자는 RFC 5321 기준이다
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    email_verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    terms_agreed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    privacy_agreed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id"),
        allowed_values_check("provider", ("google", "kakao"), "provider_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    email_at_link: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        # 삭제한 단어를 다시 추가할 수 있도록 삭제되지 않은 행끼리만 유일하게 한다 (D-24)
        Index(
            "uq_words_user_id_word_key_active",
            "user_id",
            "word_key",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_words_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = user_id_column()
    word: Mapped[str] = mapped_column(Text)
    word_key: Mapped[str] = mapped_column(Text)
    meaning: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class Wordbook(Base):
    """운영자가 넣는 공용 단어장. 회원은 읽기만 하고 고르기만 한다 (결정 D-WB01)."""

    __tablename__ = "wordbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 같은 slug로 다시 불러오면 이 행을 갱신한다 (D-WB05)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    source_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class WordbookEntry(Base):
    __tablename__ = "wordbook_entries"
    __table_args__ = (UniqueConstraint("wordbook_id", "word_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wordbook_id: Mapped[int] = mapped_column(
        ForeignKey("wordbooks.id", ondelete="CASCADE"), index=True
    )
    word: Mapped[str] = mapped_column(Text)
    # 대소문자만 다른 단어를 같은 단어로 보는 기준이다 (D-24)
    word_key: Mapped[str] = mapped_column(Text)
    meaning: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)


class UserWordbook(Base):
    """회원이 담은 단어장. 제외하면 행을 지운다."""

    __tablename__ = "user_wordbooks"

    user_id: Mapped[int] = user_id_column(primary_key=True)
    wordbook_id: Mapped[int] = mapped_column(
        ForeignKey("wordbooks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    added_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        UniqueConstraint("user_id", "day", "word_id"),
        Index("ix_plan_items_user_id_day", "user_id", "day"),
        allowed_values_check("assigned_type", ("new", "review", "wrong"), "assigned_type_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = user_id_column()
    day: Mapped[int] = mapped_column(Integer)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True)
    assigned_type: Mapped[str] = mapped_column(String(10))
    done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    position: Mapped[int] = mapped_column(Integer)


class UserSetting(Base):
    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("daily_new_count >= 1", name="daily_new_count_min"),
        allowed_values_check("test_format", TEST_FORMATS, "test_format_allowed"),
        allowed_values_check("test_direction", TEST_DIRECTIONS, "test_direction_allowed"),
    )

    user_id: Mapped[int] = user_id_column(primary_key=True)
    daily_new_count: Mapped[int] = default_setting_column("daily_new_count")
    daily_review_count: Mapped[int] = default_setting_column("daily_review_count")
    daily_wrong_count: Mapped[int] = default_setting_column("daily_wrong_count")
    wrong_threshold: Mapped[int] = default_setting_column("wrong_threshold")
    test_format: Mapped[str] = mapped_column(
        String(20),
        default=DEFAULT_SETTINGS["test_format"],
        server_default=DEFAULT_SETTINGS["test_format"],
    )
    test_direction: Mapped[str] = mapped_column(
        String(10),
        default=DEFAULT_SETTINGS["test_direction"],
        server_default=DEFAULT_SETTINGS["test_direction"],
    )
    current_day: Mapped[int] = default_setting_column("current_day")
    # 가리키던 진도 항목이 지워지면 커서를 비운다 (데이터 모델 §3.4)
    memorize_cursor_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_items.id", ondelete="SET NULL"), index=True
    )


class StudyRecord(Base):
    __tablename__ = "study_records"

    user_id: Mapped[int] = user_id_column(primary_key=True)
    # 단어는 소프트 삭제하므로 단어 행을 직접 지우는 일은 없다. 실수로 지우면 오류가 나게 둔다 (D-W07)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), primary_key=True, index=True)
    memorized_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    first_memorized_day: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_memorized_date: Mapped[date | None] = mapped_column(Date)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_wrong_date: Mapped[date | None] = mapped_column(Date)


class TestAttempt(Base):
    __tablename__ = "test_attempts"
    __table_args__ = (
        Index("ix_test_attempts_status_expires_at", "status", "expires_at"),
        allowed_values_check("test_format", TEST_FORMATS, "test_format_allowed"),
        allowed_values_check("test_direction", TEST_DIRECTIONS, "test_direction_allowed"),
        allowed_values_check("status", ("open", "submitted", "expired"), "status_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    test_format: Mapped[str] = mapped_column(String(20))
    test_direction: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class TestAttemptItem(Base):
    __tablename__ = "test_attempt_items"
    __table_args__ = (
        UniqueConstraint("attempt_id", "position"),
        allowed_values_check("direction", ("en_ko", "ko_en"), "direction_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    question: Mapped[str] = mapped_column(Text)
    choices: Mapped[str | None] = mapped_column(Text)
    correct_index: Mapped[int | None] = mapped_column(Integer)
    answers: Mapped[str] = mapped_column(Text)


class TestSession(Base):
    __tablename__ = "test_sessions"
    __table_args__ = (
        Index("ix_test_sessions_user_id_taken_at", "user_id", "taken_at"),
        CheckConstraint("score <= total", name="score_within_total"),
        allowed_values_check("test_format", TEST_FORMATS, "test_format_allowed"),
        allowed_values_check("test_direction", TEST_DIRECTIONS, "test_direction_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = user_id_column()
    # 한 시험 세트는 한 번만 제출된다 (데이터 모델 §3.8)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id"), unique=True)
    taken_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    test_format: Mapped[str] = mapped_column(String(20))
    test_direction: Mapped[str] = mapped_column(String(10))
    total: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        # 로그인 세션은 회원만, 가입 대기 세션은 소셜 제공자만 가진다 (데이터 모델 §3.10)
        CheckConstraint(
            "(user_id IS NOT NULL AND pending_provider IS NULL)"
            " OR (user_id IS NULL AND pending_provider IS NOT NULL)",
            name="login_or_pending",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(SHA256_HEX_LENGTH))
    csrf_token_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH))
    pending_provider: Mapped[str | None] = mapped_column(String(20))
    pending_provider_user_id: Mapped[str | None] = mapped_column(String(255))
    pending_display_name: Mapped[str | None] = mapped_column(String(100))


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        allowed_values_check("purpose", ("verify_email", "reset_password"), "purpose_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (
        # 잠금 판정은 계정과 IP를 함께 세므로 각각 시간순으로 찾을 수 있게 한다 (데이터 모델 §3.12)
        Index("ix_login_attempts_account_key_hash_created_at", "account_key_hash", "created_at"),
        Index("ix_login_attempts_ip_hash_created_at", "ip_hash", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_key_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH))
    ip_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH))
    action: Mapped[str] = mapped_column(String(30))
    # 30일이 지난 기록을 지울 때 쓴다
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)

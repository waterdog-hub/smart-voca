#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - DB 엔진, 테이블 기반 클래스, UTC 시각 타입을 정의한다
# 파일 위치: src/web/db/base.py

from datetime import datetime, timezone

from sqlalchemy import DateTime, Engine, MetaData, create_engine, event, make_url, text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

# 제약 이름을 DB 자동 이름에 맡기면 이후 마이그레이션에서 지목하기 어려워 규칙을 정한다
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator):
    """모든 시각을 UTC로 저장하고 UTC로 돌려준다 (D-W11)."""

    # SQLite는 시간대를 저장하지 않으므로 DB 종류와 상관없이 앱에서 UTC를 보장한다
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            # 시간대 없는 값은 어느 시간대인지 알 수 없어 잘못 저장하기 전에 막는다
            raise ValueError("시간대 정보가 없는 시각은 저장할 수 없습니다.")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    is_sqlite = url.get_backend_name() == "sqlite"
    # FastAPI가 동기 함수를 여러 스레드에서 실행하므로 SQLite 연결의 스레드 제한을 푼다
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

    if is_sqlite:
        # SQLite는 기본적으로 외래 키를 검사하지 않아 PostgreSQL과 동작이 달라진다
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def check_database(engine: Engine) -> None:
    """DB에 연결할 수 없으면 SQLAlchemy 예외를 던진다."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

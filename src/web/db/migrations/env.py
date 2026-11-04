#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - Alembic 마이그레이션 실행 환경
# 파일 위치: src/web/db/migrations/env.py

from logging.config import fileConfig

from alembic import context

from web.db import tables  # noqa: F401  (테이블을 메타데이터에 등록한다)
from web.db.base import Base, UtcDateTime, make_engine
from web.settings import Settings

config = context.config

# 테스트에서 프로그램으로 실행할 때는 로그 설정을 건드리지 않는다
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def render_item(type_, obj, autogen_context):
    # 마이그레이션 파일이 앱 코드에 묶이지 않도록 표준 타입으로 기록한다
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations() -> None:
    # 테스트는 임시 DB 주소를 직접 넘기고, 평소에는 앱 설정을 그대로 쓴다
    database_url = config.get_main_option("sqlalchemy.url") or Settings().database_url
    engine = make_engine(database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            # SQLite는 ALTER TABLE 기능이 제한적이라 테이블을 새로 만드는 방식으로 바꾼다
            render_as_batch=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("오프라인 마이그레이션은 쓰지 않습니다. DB에 연결해서 실행하세요.")

run_migrations()

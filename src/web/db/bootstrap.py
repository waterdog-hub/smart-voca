#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-25 - smart-voca - 학교 서버에서 시작할 때 DB 테이블을 만들고 공용 단어장을 넣는다 (VOCA-NFR-003)
# 파일 위치: src/web/db/bootstrap.py
#
# 학교 서버는 빈 /data 에서 앱을 띄우고, 사람이 alembic 명령을 실행할 수 없다.
# 그래서 앱이 시작할 때 스스로 마이그레이션을 적용하고, 단어장이 하나도 없을 때만 공용 단어장을 넣는다.

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from web.db.base import make_session_factory
from web.repositories import wordbook_repository
from web.services.wordbook_loader import WordbookFileError, load_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
WORDBOOK_MANIFEST = PROJECT_ROOT / "data" / "wordbooks.json"

logger = logging.getLogger("smart_voca.bootstrap")


def upgrade_to_latest(database_url: str) -> None:
    """alembic upgrade head 를 코드로 실행한다. 이미 최신이면 아무 일도 하지 않는다."""
    # alembic.ini 는 개발 PC에서 명령으로 쓸 때만 필요하다. 여기서는 같은 설정을 코드로 준다
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logging"] = False
    command.upgrade(config, "head")


def load_wordbooks_if_empty(engine: Engine, manifest_path: Path = WORDBOOK_MANIFEST) -> int:
    """단어장이 하나도 없을 때만 공용 단어장을 넣는다. 넣은 단어장 수를 돌려준다."""
    with make_session_factory(engine)() as db:
        if wordbook_repository.list_wordbooks(db):
            return 0
        try:
            results = load_manifest(db, manifest_path)
        except (WordbookFileError, OSError) as error:
            # 단어장이 없어도 회원은 직접 단어를 등록할 수 있으므로 시작은 계속한다
            logger.warning("공용 단어장을 넣지 못했습니다: %s", error)
            return 0
    return len(results)


def prepare_database(database_url: str, engine: Engine) -> None:
    upgrade_to_latest(database_url)
    loaded = load_wordbooks_if_empty(engine)
    if loaded:
        logger.info("공용 단어장 %d개를 넣었습니다.", loaded)

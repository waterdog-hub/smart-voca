#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 운영자가 data/wordbooks.json의 공용 단어장을 DB에 넣는다 (결정 D-WB05)
# 파일 위치: ai-agent/scripts/load_wordbooks.py
#
# 실행 (프로젝트 루트): .venv\Scripts\python ai-agent/scripts/load_wordbooks.py
# 대상 DB는 .env의 DATABASE_URL이다. 같은 slug를 다시 실행하면 그 단어장의 항목을 통째로 바꾼다.
# 회원이 이미 담은 단어는 복사본이라 바뀌지 않는다.

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from web.db.base import make_engine, make_session_factory  # noqa: E402
from web.services.wordbook_loader import WordbookFileError, load_manifest  # noqa: E402
from web.settings import Settings  # noqa: E402

DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "wordbooks.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="공용 단어장을 DB에 넣습니다.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="단어장 목록 파일")
    manifest_path = parser.parse_args().manifest

    engine = make_engine(Settings().database_url)
    try:
        with make_session_factory(engine)() as db:
            results = load_manifest(db, manifest_path)
    except WordbookFileError as error:
        print(f"단어장을 넣지 못했습니다: {error}")
        return 1
    finally:
        engine.dispose()

    for result in results:
        state = "새로 만듦" if result.created else "갱신"
        print(f"{result.slug}: {state}, 단어 {result.entry_count}개")
        if result.skipped_duplicate:
            print(f"  중복으로 건너뜀 {result.skipped_duplicate}개")
        if result.invalid_count:
            print(f"  형식 오류로 건너뜀 {result.invalid_count}개")
            for line_number, reason in result.invalid_rows[:10]:
                print(f"    {line_number}번째 줄: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

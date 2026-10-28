#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 경로, 기본 설정값, CSV 인코딩 상수 정의
# 파일 위치: src/config.py

from pathlib import Path

# 프로젝트 루트 (src의 상위 폴더)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

WORDS_CSV_PATH = DATA_DIR / "words.csv"
SETTINGS_CSV_PATH = DATA_DIR / "settings.csv"
RECORD_CSV_PATH = DATA_DIR / "study_record.csv"
PLAN_CSV_PATH = DATA_DIR / "day_plan.csv"
TEST_HISTORY_CSV_PATH = DATA_DIR / "test_history.csv"
# 단어장을 CSV로 덮어쓰기 전에 남기는 백업 폴더 (설계 D-22)
BACKUP_DIR = DATA_DIR / "backup"

# 엑셀에서 한글이 깨지지 않도록 BOM을 붙인 UTF-8을 쓴다 (설계 D-01)
CSV_ENCODING = "utf-8-sig"

# 설정 파일이 없거나 항목이 빠졌을 때 쓰는 기본값 (설계서 §4.2)
DEFAULT_SETTINGS = {
    "daily_new_count": 20,
    "daily_review_count": 5,
    "daily_wrong_count": 5,
    "wrong_threshold": 3,
    "test_format": "multiple",   # multiple(객관식) / subjective(주관식)
    "test_direction": "en_ko",   # en_ko / ko_en / both
    "current_day": 0,
}

# 시험 객관식 보기 개수 (정답 1 + 오답 3)
CHOICE_COUNT = 4

# 진도 항목 유형(assigned_type) 코드를 화면 라벨로 바꾸는 대응표
ASSIGNED_TYPE_LABELS = {"new": "신규", "review": "복습", "wrong": "오답"}
# 화면 표시용 라벨과 설정값(영문 코드) 대응표
TEST_FORMAT_LABELS = {"객관식": "multiple", "주관식": "subjective"}
TEST_DIRECTION_LABELS = {"영→한": "en_ko", "한→영": "ko_en", "양방향": "both"}

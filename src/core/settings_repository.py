#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 설정 CSV 읽기·쓰기, 손상된 값은 기본값으로 복구 (SettingsRepository)
# 파일 위치: src/core/settings_repository.py

import csv
from dataclasses import asdict
from pathlib import Path
from typing import List, Tuple

from config import CSV_ENCODING, DEFAULT_SETTINGS
from models import Settings

ALLOWED_TEST_FORMATS = ("multiple", "subjective")
ALLOWED_TEST_DIRECTIONS = ("en_ko", "ko_en", "both")
INT_KEYS = ("daily_new_count", "daily_review_count", "daily_wrong_count",
            "wrong_threshold", "current_day")


class SettingsRepository:
    """settings.csv(key,value)를 읽고 쓴다. 잘못된 값은 기본값으로 되돌린다 (설계 D-05)."""

    def load(self, path: Path) -> Tuple[Settings, List[str]]:
        """설정을 읽는다.

        반환: (설정, 경고 메시지 목록)
        파일이 없으면 기본값을 쓴다. 값이 잘못된 항목은 기본값으로 바꾸고 경고를 남긴다.
        """
        values = dict(DEFAULT_SETTINGS)
        warnings: List[str] = []

        if path.exists():
            with open(path, "r", encoding=CSV_ENCODING, newline="") as csv_file:
                for row in csv.reader(csv_file):
                    if len(row) < 2 or row[0].strip() == "key":
                        continue
                    key = row[0].strip()
                    if key in DEFAULT_SETTINGS:
                        values[key] = row[1].strip()

        for key in INT_KEYS:
            values[key], warning = self._to_int(key, values[key])
            if warning:
                warnings.append(warning)

        if values["test_format"] not in ALLOWED_TEST_FORMATS:
            warnings.append(f"test_format 값이 잘못되어 기본값으로 바꿨습니다: {values['test_format']}")
            values["test_format"] = DEFAULT_SETTINGS["test_format"]

        if values["test_direction"] not in ALLOWED_TEST_DIRECTIONS:
            warnings.append(f"test_direction 값이 잘못되어 기본값으로 바꿨습니다: {values['test_direction']}")
            values["test_direction"] = DEFAULT_SETTINGS["test_direction"]

        return Settings(**values), warnings

    def save(self, settings: Settings, path: Path) -> None:
        """설정을 key,value 형식으로 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=CSV_ENCODING, newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["key", "value"])
            for key, value in asdict(settings).items():
                writer.writerow([key, value])

    def _to_int(self, key: str, raw_value) -> Tuple[int, str]:
        """정수로 바꾼다. 실패하면 기본값과 경고 메시지를 돌려준다."""
        try:
            number = int(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_SETTINGS[key], f"{key} 값이 숫자가 아니어서 기본값으로 바꿨습니다: {raw_value}"
        if number < 0:
            return DEFAULT_SETTINGS[key], f"{key} 값이 음수여서 기본값으로 바꿨습니다: {raw_value}"
        return number, ""

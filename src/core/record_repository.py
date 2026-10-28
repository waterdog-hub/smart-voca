#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 단어별 학습·오답 기록 CSV 읽기·쓰기 (RecordRepository)
# 파일 위치: src/core/record_repository.py

import csv
from dataclasses import asdict, fields
from pathlib import Path
from typing import Dict

from core.file_utils import atomic_write
from config import CSV_ENCODING
from models import StudyRecord

RECORD_FIELDS = [field.name for field in fields(StudyRecord)]
INT_FIELDS = ("memorized_count", "first_memorized_day", "wrong_count")


class RecordRepository:
    """study_record.csv를 읽고 쓴다. 키는 단어 문자열이다."""

    def load(self, path: Path) -> Dict[str, StudyRecord]:
        """단어 → 기록 사전을 돌려준다. 파일이 없으면 빈 사전이다."""
        records: Dict[str, StudyRecord] = {}
        if not path.exists():
            return records

        with open(path, "r", encoding=CSV_ENCODING, newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                word_text = (row.get("word") or "").strip()
                if not word_text:
                    continue
                values = {name: (row.get(name) or "").strip() for name in RECORD_FIELDS}
                for name in INT_FIELDS:
                    values[name] = int(values[name] or 0)
                records[word_text] = StudyRecord(**values)
        return records

    def save(self, records: Dict[str, StudyRecord], path: Path) -> None:
        """기록 사전을 CSV로 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with atomic_write(path, CSV_ENCODING) as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=RECORD_FIELDS)
            writer.writeheader()
            for record in records.values():
                writer.writerow(asdict(record))

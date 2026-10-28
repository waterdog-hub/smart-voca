#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 시험 결과 기록 CSV 읽기·쓰기 (TestHistoryRepository)
# 파일 위치: src/core/test_history_repository.py
import csv
from dataclasses import asdict, fields
from pathlib import Path
from typing import List

from config import CSV_ENCODING
from models import TestHistory

HISTORY_FIELDS = [field.name for field in fields(TestHistory)]


class TestHistoryRepository:
    """test_history.csv를 읽고 쓴다. 시험 한 세트가 한 행이다."""

    def load(self, path: Path) -> List[TestHistory]:
        """시험 기록 목록을 읽는다. 파일이 없으면 빈 목록이다."""
        if not path.exists():
            return []
        entries: List[TestHistory] = []
        with open(path, "r", encoding=CSV_ENCODING, newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                if not (row.get("taken_at") or "").strip():
                    continue
                entries.append(TestHistory(
                    taken_at=row["taken_at"].strip(),
                    test_format=row["test_format"].strip(),
                    test_direction=row["test_direction"].strip(),
                    total=int(row["total"] or 0),
                    score=int(row["score"] or 0),
                ))
        return entries

    def save(self, entries: List[TestHistory], path: Path) -> None:
        """시험 기록 목록 전체를 CSV로 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=CSV_ENCODING, newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=HISTORY_FIELDS)
            writer.writeheader()
            for entry in entries:
                writer.writerow(asdict(entry))

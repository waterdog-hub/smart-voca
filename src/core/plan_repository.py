#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 일차별 진도 CSV 읽기·쓰기 (PlanRepository)
# 파일 위치: src/core/plan_repository.py

import csv
from pathlib import Path
from typing import List

from config import CSV_ENCODING
from models import DayPlanItem

PLAN_FIELDS = ["day", "word", "assigned_type", "done"]


class PlanRepository:
    """day_plan.csv를 읽고 쓴다. 모든 일차의 진도를 한 파일에 둔다."""

    def load(self, path: Path) -> List[DayPlanItem]:
        """진도 목록을 읽는다. 파일이 없으면 빈 목록이다."""
        if not path.exists():
            return []

        items: List[DayPlanItem] = []
        with open(path, "r", encoding=CSV_ENCODING, newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                if not (row.get("word") or "").strip():
                    continue
                items.append(DayPlanItem(
                    day=int(row["day"]),
                    word=row["word"].strip(),
                    assigned_type=row["assigned_type"].strip(),
                    done=row["done"].strip() == "1",
                ))
        return items

    def save(self, items: List[DayPlanItem], path: Path) -> None:
        """진도 목록 전체를 CSV로 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=CSV_ENCODING, newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(PLAN_FIELDS)
            for item in items:
                writer.writerow([item.day, item.word, item.assigned_type, 1 if item.done else 0])

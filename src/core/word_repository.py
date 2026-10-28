#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 단어장 CSV 읽기·쓰기 (WordRepository)
# 파일 위치: src/core/word_repository.py

import csv
from pathlib import Path
from typing import List, Tuple

from core.file_utils import atomic_write
from config import CSV_ENCODING
from models import Word

REQUIRED_HEADER = ["word", "meaning"]


class WordRepository:
    """words.csv를 읽고 쓴다. 파일 형식은 이 클래스만 안다."""

    def load(self, path: Path) -> Tuple[List[Word], int]:
        """단어 목록을 읽는다.

        반환: (단어 목록, 건너뛴 행 수)
        중복 단어는 첫 항목만 남기고, 빈 word/meaning 행은 버린다.
        헤더가 word,meaning이 아니면 ValueError를 던진다.
        """
        with open(path, "r", encoding=CSV_ENCODING, newline="") as csv_file:
            reader = csv.reader(csv_file)
            header = [column.strip() for column in next(reader, [])]
            if header != REQUIRED_HEADER:
                raise ValueError("단어 파일 형식이 맞지 않습니다. 첫 줄은 word,meaning이어야 합니다.")

            words: List[Word] = []
            seen_words = set()
            skipped_count = 0
            for row in reader:
                if len(row) < 2:
                    skipped_count += 1
                    continue
                word_text = row[0].strip()
                meaning_text = row[1].strip()
                if not word_text or not meaning_text:
                    skipped_count += 1
                    continue
                if word_text in seen_words:
                    skipped_count += 1
                    continue
                seen_words.add(word_text)
                meaning_list = [item.strip() for item in meaning_text.split("/") if item.strip()]
                words.append(Word(word=word_text, meaning_list=meaning_list))
        return words, skipped_count

    def save(self, words: List[Word], path: Path) -> None:
        """단어 목록을 헤더와 함께 CSV로 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with atomic_write(path, CSV_ENCODING) as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(REQUIRED_HEADER)
            for word in words:
                writer.writerow([word.word, word.meaning_text])

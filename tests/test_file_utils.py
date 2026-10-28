#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 안전한 저장(임시 파일 후 교체)과 백업 단위 테스트
# 파일 위치: tests/test_file_utils.py

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.file_utils import atomic_write, backup_file  # noqa: E402


class AtomicWriteTest(unittest.TestCase):

    def test_writes_new_file_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.csv"
            with atomic_write(path, "utf-8-sig") as file:
                file.write("word,meaning\napple,사과\n")

            self.assertEqual(path.read_text(encoding="utf-8-sig"), "word,meaning\napple,사과\n")
            self.assertFalse((Path(temp_dir) / "sample.csv.tmp").exists())

    def test_failure_keeps_original_file_intact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.csv"
            path.write_text("original", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                with atomic_write(path, "utf-8") as file:
                    file.write("partial")
                    raise RuntimeError("저장 중 오류")

            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            self.assertFalse((Path(temp_dir) / "sample.csv.tmp").exists())


class BackupFileTest(unittest.TestCase):

    def test_copies_file_into_backup_folder_with_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "words.csv"
            source.write_text("word,meaning\nrun,달리다\n", encoding="utf-8")
            backup_dir = Path(temp_dir) / "backup"

            backup_path = backup_file(source, backup_dir)

            self.assertIsNotNone(backup_path)
            self.assertEqual(backup_path.parent, backup_dir)
            self.assertTrue(backup_path.name.startswith("words_"))
            self.assertEqual(backup_path.read_bytes(), source.read_bytes())

    def test_missing_source_gives_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertIsNone(backup_file(Path(temp_dir) / "none.csv", Path(temp_dir) / "backup"))


if __name__ == "__main__":
    unittest.main()

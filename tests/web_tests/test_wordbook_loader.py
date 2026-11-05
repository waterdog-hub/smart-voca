#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 운영자의 공용 단어장 CSV 읽기와 DB 반영 테스트 (FR-BOOK-04, 결정 D-WB05, D-WB09)
# 파일 위치: tests/web_tests/test_wordbook_loader.py

import json
import unittest
from pathlib import Path

from web_tests.support import PROJECT_ROOT, AuthTestCase

from sqlalchemy import select

from web.db.tables import Word, Wordbook, WordbookEntry
from web.services import wordbook_loader
from web.services.wordbook_loader import (
    WordbookFileError,
    WordbookSpec,
    load_manifest,
    load_wordbook,
    parse_wordbook_csv,
    read_manifest,
)

HEADER = "word,meaning\n"


def csv_bytes(body, header=HEADER):
    return (header + body).encode("utf-8")


class ParseWordbookTest(unittest.TestCase):
    def test_rows_are_read_in_file_order_with_keys(self):
        parsed = parse_wordbook_csv(csv_bytes("Apple,사과\nrun,달리다/운영하다\n"))
        self.assertEqual(
            parsed.entries,
            [("Apple", "apple", "사과"), ("run", "run", "달리다/운영하다")],
        )

    def test_values_are_trimmed_and_meanings_normalized(self):
        parsed = parse_wordbook_csv(csv_bytes('  run  ," 달리다/ /운영하다 "\n'))
        self.assertEqual(parsed.entries, [("run", "run", "달리다/운영하다")])

    def test_utf8_bom_and_cp949_are_read(self):
        body = "word,meaning\napple,사과\n"
        for name, raw in (("utf-8-sig", body.encode("utf-8-sig")), ("cp949", body.encode("cp949"))):
            with self.subTest(name):
                self.assertEqual(parse_wordbook_csv(raw).entries, [("apple", "apple", "사과")])

    def test_unreadable_bytes_are_rejected(self):
        with self.assertRaisesRegex(WordbookFileError, "읽을 수 없습니다"):
            parse_wordbook_csv(b"\xff\xfe\x00\x81")

    def test_wrong_header_is_rejected(self):
        for header in ("단어,뜻\n", "word\n", "meaning,word\n", ""):
            with self.subTest(header=header):
                with self.assertRaisesRegex(WordbookFileError, "word,meaning"):
                    parse_wordbook_csv(csv_bytes("apple,사과\n", header=header))

    def test_duplicates_ignoring_case_keep_the_first(self):
        parsed = parse_wordbook_csv(csv_bytes("apple,사과\nAPPLE,애플\nPear,배\n"))
        self.assertEqual([entry[0] for entry in parsed.entries], ["apple", "Pear"])
        self.assertEqual(parsed.skipped_duplicate, 1)

    def test_blank_lines_are_not_errors(self):
        parsed = parse_wordbook_csv(csv_bytes("apple,사과\n\n\npear,배\n"))
        self.assertEqual(len(parsed.entries), 2)
        self.assertEqual(parsed.invalid_count, 0)

    def test_invalid_rows_are_reported_by_line_number_and_skipped(self):
        parsed = parse_wordbook_csv(csv_bytes("apple,사과\n,뜻만\nlonely\nthree,셋,넷\npear,배\n"))
        self.assertEqual([entry[0] for entry in parsed.entries], ["apple", "pear"])
        self.assertEqual([line for line, _ in parsed.invalid_rows], [3, 4, 5])
        self.assertEqual(parsed.invalid_count, 3)

    def test_length_limits(self):
        long_word = "x" * (wordbook_loader.MAX_WORD_LENGTH + 1)
        long_meaning = "가" * (wordbook_loader.MAX_MEANING_LENGTH + 1)
        parsed = parse_wordbook_csv(csv_bytes(f"{long_word},뜻\nword,{long_meaning}\n{'y' * 100},{'나' * 500}\n"))
        self.assertEqual(parsed.invalid_count, 2)
        self.assertEqual(len(parsed.entries), 1)

    def test_control_characters_are_invalid(self):
        parsed = parse_wordbook_csv(csv_bytes('bad\x07word,뜻\nword,"뜻\x07"\n'))
        self.assertEqual((len(parsed.entries), parsed.invalid_count), (0, 2))

    def test_reported_invalid_rows_are_capped_but_counted(self):
        body = "".join(f"w{number}\n" for number in range(wordbook_loader.MAX_REPORTED_INVALID_ROWS + 20))
        parsed = parse_wordbook_csv(csv_bytes(body))
        self.assertEqual(len(parsed.invalid_rows), wordbook_loader.MAX_REPORTED_INVALID_ROWS)
        self.assertEqual(parsed.invalid_count, wordbook_loader.MAX_REPORTED_INVALID_ROWS + 20)

    def test_row_range_picks_data_rows_inclusive(self):
        body = "".join(f"w{number},뜻{number}\n" for number in range(1, 8))
        parsed = parse_wordbook_csv(csv_bytes(body), row_range=(3, 5))
        self.assertEqual([entry[0] for entry in parsed.entries], ["w3", "w4", "w5"])

    def test_row_range_ignores_blank_lines_when_counting(self):
        parsed = parse_wordbook_csv(csv_bytes("a,1\n\nb,2\n\nc,3\n"), row_range=(2, 3))
        self.assertEqual([entry[0] for entry in parsed.entries], ["b", "c"])

    def test_row_range_past_the_end_is_empty(self):
        self.assertEqual(parse_wordbook_csv(csv_bytes("a,1\n"), row_range=(5, 9)).entries, [])

    def test_too_many_rows_are_rejected(self):
        original = wordbook_loader.MAX_WORDBOOK_ROWS
        wordbook_loader.MAX_WORDBOOK_ROWS = 3
        try:
            with self.assertRaisesRegex(WordbookFileError, "3행 이하"):
                parse_wordbook_csv(csv_bytes("a,1\nb,2\nc,3\nd,4\n"))
        finally:
            wordbook_loader.MAX_WORDBOOK_ROWS = original

    def test_oversized_file_is_rejected(self):
        raw = b"word,meaning\n" + b"a" * (5 * 1024 * 1024)
        with self.assertRaisesRegex(WordbookFileError, "5MB"):
            parse_wordbook_csv(raw)


class LoadWordbookTest(AuthTestCase):
    def spec(self, body="apple,사과\nriver,강\n", slug="book-a", title="책 A", rows=None):
        path = self.temp_path / f"{slug}.csv"
        path.write_bytes(csv_bytes(body))
        return WordbookSpec(slug, title, "설명", "출처", path, rows)

    def entries(self, db, slug="book-a"):
        book = db.scalar(select(Wordbook).where(Wordbook.slug == slug))
        return [
            (entry.position, entry.word, entry.word_key, entry.meaning)
            for entry in db.scalars(
                select(WordbookEntry).where(WordbookEntry.wordbook_id == book.id).order_by(WordbookEntry.position)
            )
        ]

    def test_new_wordbook_is_created_with_ordered_entries(self):
        with self.db() as db:
            result = load_wordbook(db, self.spec())
        self.assertEqual((result.slug, result.created, result.entry_count), ("book-a", True, 2))
        with self.db() as db:
            self.assertEqual(
                self.entries(db), [(1, "apple", "apple", "사과"), (2, "river", "river", "강")]
            )
            book = db.scalar(select(Wordbook))
            self.assertEqual((book.title, book.description, book.source_note), ("책 A", "설명", "출처"))

    def test_loading_again_replaces_info_and_entries(self):
        with self.db() as db:
            load_wordbook(db, self.spec())
        with self.db() as db:
            result = load_wordbook(db, self.spec("tree,나무\n", title="새 제목"))
        self.assertFalse(result.created)
        with self.db() as db:
            self.assertEqual(self.entries(db), [(1, "tree", "tree", "나무")])
            self.assertEqual(len(db.scalars(select(Wordbook)).all()), 1)
            self.assertEqual(db.scalar(select(Wordbook.title)), "새 제목")

    def test_reload_does_not_change_words_members_already_have(self):
        self.verified_member()
        with self.db() as db:
            load_wordbook(db, self.spec())
            book_id = db.scalar(select(Wordbook.id))
        self.client.post(f"/api/v1/wordbooks/{book_id}/add", headers=self.verified_headers())
        with self.db() as db:
            load_wordbook(db, self.spec("apple,사과(고침)\n"))
        with self.db() as db:
            rows = {row.word_key: row.meaning for row in db.scalars(select(Word))}
        self.assertEqual(rows, {"apple": "사과", "river": "강"})

    def verified_headers(self):
        return {"X-CSRF-Token": self.client.get("/api/v1/auth/session").json()["csrf_token"]}

    def test_row_range_is_applied(self):
        with self.db() as db:
            result = load_wordbook(db, self.spec("a,1\nb,2\nc,3\nd,4\n", rows=(2, 3)))
        self.assertEqual(result.entry_count, 2)
        with self.db() as db:
            self.assertEqual([entry[1] for entry in self.entries(db)], ["b", "c"])

    def test_empty_result_keeps_the_existing_wordbook(self):
        with self.db() as db:
            load_wordbook(db, self.spec())
        for bad_spec in (self.spec(""), self.spec("a,1\n", rows=(9, 9)), self.spec(",뜻\n")):
            with self.subTest(rows=bad_spec.row_range):
                with self.db() as db:
                    with self.assertRaisesRegex(WordbookFileError, "넣을 수 있는 단어가 없습니다"):
                        load_wordbook(db, bad_spec)
        with self.db() as db:
            self.assertEqual(len(self.entries(db)), 2)

    def test_missing_file_is_reported(self):
        spec = self.spec()
        spec.file = self.temp_path / "missing.csv"
        with self.db() as db:
            with self.assertRaisesRegex(WordbookFileError, "읽을 수 없습니다"):
                load_wordbook(db, spec)
            self.assertEqual(db.scalars(select(Wordbook)).all(), [])


class ManifestTest(AuthTestCase):
    def write_manifest(self, wordbooks, name="wordbooks.json"):
        path = self.temp_path / name
        path.write_text(json.dumps({"wordbooks": wordbooks}, ensure_ascii=False), "utf-8")
        return path

    def item(self, **overrides):
        return {
            "slug": "book-a", "title": "책 A", "description": "설명", "source_note": "출처",
            "file": "a.csv", **overrides,
        }

    def test_valid_manifest_is_read(self):
        specs = read_manifest(self.write_manifest([self.item(rows=[1, 3]), self.item(slug="book-b")]))
        self.assertEqual([spec.slug for spec in specs], ["book-a", "book-b"])
        self.assertEqual(specs[0].row_range, (1, 3))
        self.assertIsNone(specs[1].row_range)
        self.assertEqual(specs[0].file, (self.temp_path / "a.csv").resolve())

    def test_invalid_manifests_are_rejected(self):
        cases = {
            "slug with capital": [self.item(slug="Book")],
            "slug with space": [self.item(slug="a b")],
            "slug too long": [self.item(slug="a" * 51)],
            "missing title": [self.item(title="")],
            "missing file": [self.item(file=None)],
            "title too long": [self.item(title="가" * 101)],
            "duplicate slug": [self.item(), self.item()],
            "path escape": [self.item(file="../outside.csv")],
            "absolute path": [self.item(file=str(Path(self.temp_path.anchor) / "x.csv"))],
            "rows reversed": [self.item(rows=[5, 2])],
            "rows zero": [self.item(rows=[0, 3])],
            "rows text": [self.item(rows=["1", "3"])],
            "rows bool": [self.item(rows=[True, 3])],
            "rows one number": [self.item(rows=[1])],
            "item is not object": ["book"],
            "empty list": [],
        }
        for name, wordbooks in cases.items():
            with self.subTest(name):
                with self.assertRaises(WordbookFileError):
                    read_manifest(self.write_manifest(wordbooks))

    def test_broken_or_missing_manifest_is_reported(self):
        broken = self.temp_path / "broken.json"
        broken.write_text("{ not json", "utf-8")
        for path in (broken, self.temp_path / "nothing.json"):
            with self.subTest(path.name):
                with self.assertRaisesRegex(WordbookFileError, "목록 파일"):
                    read_manifest(path)

    def test_load_manifest_loads_every_wordbook(self):
        (self.temp_path / "a.csv").write_bytes(csv_bytes("a,1\nb,2\nc,3\n"))
        manifest = self.write_manifest([self.item(rows=[1, 2]), self.item(slug="book-b", rows=[3, 3])])
        with self.db() as db:
            results = load_manifest(db, manifest)
        self.assertEqual([(r.slug, r.entry_count) for r in results], [("book-a", 2), ("book-b", 1)])

    def test_project_sample_manifest_loads_the_whole_sample_file(self):
        with self.db() as db:
            results = load_manifest(db, PROJECT_ROOT / "data" / "wordbooks.json")
        self.assertEqual(len(results), 4)
        self.assertEqual(sum(result.entry_count for result in results), 1988)
        self.assertEqual(sum(result.invalid_count + result.skipped_duplicate for result in results), 0)
        with self.db() as db:
            keys = db.scalars(select(WordbookEntry.word_key)).all()
        self.assertEqual(len(keys), len(set(keys)))  # 단어장 사이에도 겹치는 단어가 없다

    def test_project_sample_wordbooks_are_named_by_level_in_order(self):
        # 단계 이름은 사용자 요청이다 (이슈 #17 후속). 순서가 곧 목록의 앞뒤다
        manifest = read_manifest(PROJECT_ROOT / "data" / "wordbooks.json")
        self.assertEqual([spec.title for spec in manifest], ["초급 단어", "중급 단어", "고급 단어", "심화 단어"])


if __name__ == "__main__":
    unittest.main()

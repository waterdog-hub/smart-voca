#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - CSV 가져오기·내보내기, 파일 제한, 수식 주입 방지 테스트
# 파일 위치: tests/web_tests/test_words_csv.py

import csv
import io
import unittest
from datetime import timedelta
from unittest import mock

from web_tests.support import PROJECT_ROOT
from web_tests.test_words_api import DELETE_API, WORDS_API, WordsTestCase

from sqlalchemy import select

from web.db.tables import LoginAttempt, StudyRecord, User, Word
from web.repositories import word_repository
from web.security import csv_guard

IMPORT_API = f"{WORDS_API}/import"
EXPORT_API = f"{WORDS_API}/export"
HEADER = "word,meaning\n"


class CsvTestCase(WordsTestCase):
    def upload(self, content, name="words.csv"):
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        return self.client.post(
            IMPORT_API, files={"file": (name, data, "text/csv")}, headers=self.headers
        )

    def import_ok(self, content):
        response = self.upload(content)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def exported_rows(self):
        response = self.client.get(EXPORT_API)
        self.assertEqual(response.status_code, 200)
        return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))


class ImportTest(CsvTestCase):
    def test_import_adds_words_in_file_order(self):
        result = self.import_ok(HEADER + "zebra,얼룩말\napple,사과\nmango,망고/열매\n")
        self.assertEqual(result["added"], 3)
        self.assertEqual(result["skipped_duplicate"], 0)
        self.assertEqual(result["skipped_invalid"], 0)
        self.assertEqual(self.words_of(sort="created"), ["zebra", "apple", "mango"])

    def test_encodings(self):
        cases = {
            "utf8_bom": ("﻿" + HEADER + "apple,사과\n").encode("utf-8"),
            "utf8": (HEADER + "pear,배\n").encode("utf-8"),
            "cp949": (HEADER + "plum,자두\n").encode("cp949"),
            "crlf": (HEADER.replace("\n", "\r\n") + "kiwi,키위\r\n").encode("utf-8"),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self.import_ok(content)["added"], 1)
        self.assertEqual(self.words_of(sort="created"), ["apple", "pear", "plum", "kiwi"])
        self.assertEqual(self.listing(q="자두")["total"], 1)

    def test_duplicates_are_skipped_keeping_first(self):
        self.add("apple", "기존 뜻")
        result = self.import_ok(HEADER + "APPLE,새 뜻\npear,배\nPEAR,다른 뜻\n")
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped_duplicate"], 2)
        items = {item["word"]: item["meaning"] for item in self.listing()["items"]}
        self.assertEqual(items, {"apple": "기존 뜻", "pear": "배"})

    def test_invalid_rows_are_reported_by_line_number(self):
        content = (
            HEADER
            + "good,좋다\n"  # 2
            + "onlyword\n"  # 3
            + ",뜻만\n"  # 4
            + "wordonly,\n"  # 5
            + "\n"  # 6 빈 줄은 오류가 아니다
            + "too,many,columns\n"  # 7
            + ("x" * 101) + ",너무 길다\n"  # 8
            + "extra,빈 열 허용,,\n"  # 9
        )
        result = self.import_ok(content)
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["skipped_invalid"], 5)
        self.assertEqual([row["row"] for row in result["invalid_rows"]], [3, 4, 5, 7, 8])
        self.assertTrue(all(row["reason"] for row in result["invalid_rows"]))

    def test_invalid_row_report_does_not_echo_content(self):
        result = self.import_ok(HEADER + "only-secret-text\n")
        self.assertNotIn("only-secret-text", str(result))

    def test_invalid_row_list_is_capped(self):
        result = self.import_ok(HEADER + "bad\n" * 150)
        self.assertEqual(result["skipped_invalid"], 150)
        self.assertEqual(len(result["invalid_rows"]), 100)

    def test_quoted_comma_and_newline_line_numbers(self):
        result = self.import_ok(HEADER + 'run,"달리다, 뛰다"\nbad\n')
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["invalid_rows"][0]["row"], 3)
        self.assertEqual(self.listing()["items"][0]["meaning"], "달리다, 뛰다")

    def test_deleted_word_is_revived_with_record(self):
        item = self.add("apple", "옛 뜻")
        self.add_plan_and_record(item["id"])
        self.client.post(DELETE_API, json={"ids": [item["id"]]}, headers=self.headers)
        result = self.import_ok(HEADER + "Apple,새 뜻\n")
        self.assertEqual(result["added"], 1)
        listed = self.listing()["items"][0]
        self.assertEqual(listed["id"], item["id"])
        self.assertEqual(listed["word"], "Apple")
        self.assertEqual(listed["meaning"], "새 뜻")
        with self.db() as db:
            self.assertEqual(db.scalar(select(StudyRecord)).wrong_count, 3)

    def test_empty_body_with_header_only_is_ok(self):
        self.assertEqual(self.import_ok(HEADER)["added"], 0)

    def test_sample_word_file_imports_completely(self):
        raw = (PROJECT_ROOT / "data" / "words.csv").read_bytes()
        expected = len(list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))) - 1
        result = self.import_ok(raw)
        self.assertEqual(
            result["added"] + result["skipped_duplicate"] + result["skipped_invalid"], expected
        )
        self.assertEqual(self.listing()["total"], result["added"])
        self.assertGreater(result["added"], 1000)


class ImportRejectionTest(CsvTestCase):
    def assert_file_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        self.assertEqual(response.json()["error"]["code"], code)
        self.assertEqual(self.listing()["total"], 0)

    def test_wrong_header_saves_nothing(self):
        for content in ("word,mean\napple,사과\n", "apple,사과\n", "", "word\napple\n"):
            with self.subTest(content=content[:12]):
                response = self.upload(content)
                self.assert_file_error(response, 400, "VALIDATION_FAILED")
                self.assertIn("file", response.json()["error"]["fields"])

    def test_undecodable_file_is_rejected(self):
        self.assert_file_error(self.upload(b"\xff\xfe\x00\x81\xff"), 400, "VALIDATION_FAILED")

    def test_missing_file_field_is_rejected(self):
        response = self.client.post(IMPORT_API, headers=self.headers)
        self.assert_file_error(response, 400, "VALIDATION_FAILED")

    def test_file_size_limit(self):
        padding = "x" * (csv_guard.MAX_UPLOAD_BYTES + 1 - len(HEADER))
        self.assert_file_error(self.upload(HEADER + padding), 413, "FILE_TOO_LARGE")

    def test_row_limit(self):
        over = HEADER + "".join(f"w{i},뜻\n" for i in range(csv_guard.MAX_IMPORT_ROWS + 1))
        self.assert_file_error(self.upload(over), 413, "FILE_TOO_LARGE")

    def test_exact_row_limit_is_accepted(self):
        exact = HEADER + "".join(f"w{i},뜻\n" for i in range(csv_guard.MAX_IMPORT_ROWS))
        self.assertEqual(self.import_ok(exact)["added"], csv_guard.MAX_IMPORT_ROWS)

    def test_oversized_field_is_rejected_without_crashing(self):
        self.assert_file_error(self.upload(HEADER + "a," + "b" * 200_000 + "\n"), 400, "VALIDATION_FAILED")

    def test_conflict_during_import_saves_nothing(self):
        real_list = word_repository.list_all_words_including_deleted

        def list_then_conflict(db, user_id):
            rows = real_list(db, user_id)
            # 목록을 읽은 뒤 다른 요청이 같은 단어를 추가한 상황을 만든다
            with self.db() as other_session:
                other_session.add(Word(user_id=user_id, word="pear", word_key="pear", meaning="배"))
                other_session.commit()
            return rows

        with mock.patch.object(
            word_repository, "list_all_words_including_deleted", list_then_conflict
        ):
            response = self.upload(HEADER + "apple,사과\npear,배\nplum,자두\n")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.words_of(), ["pear"])

    def test_import_is_limited_per_hour(self):
        for _ in range(20):
            self.assertEqual(self.upload(HEADER).status_code, 200)
        response = self.upload(HEADER)
        self.assertEqual(response.status_code, 429)
        self.assertGreater(response.json()["error"]["retry_after"], 0)

    def test_failed_uploads_count_toward_limit(self):
        for _ in range(20):
            self.assertEqual(self.upload("wrong header\n").status_code, 400)
        self.assertEqual(self.upload(HEADER).status_code, 429)

    def test_limit_ends_after_an_hour(self):
        for _ in range(20):
            self.upload(HEADER)
        with self.db() as db:
            for attempt in db.scalars(select(LoginAttempt)):
                attempt.created_at -= timedelta(hours=1, seconds=1)
            db.commit()
        self.assertEqual(self.upload(HEADER).status_code, 200)

    def test_import_limit_is_per_member(self):
        for _ in range(20):
            self.upload(HEADER)
        other = self.make_auth_client()
        headers = self.verified_member("other@example.com", client=other)
        response = other.post(
            IMPORT_API, files={"file": ("w.csv", HEADER.encode())}, headers=headers
        )
        self.assertEqual(response.status_code, 200)

    def test_attempt_record_has_no_plain_email(self):
        self.upload(HEADER)
        with self.db() as db:
            email = db.scalar(select(User.email))
            attempt = db.scalar(select(LoginAttempt).where(LoginAttempt.action == "import"))
        self.assertNotIn(email, attempt.account_key_hash)
        self.assertEqual(len(attempt.account_key_hash), 64)


class ExportTest(CsvTestCase):
    def test_export_format(self):
        self.add("apple", "사과")
        response = self.client.get(EXPORT_API)
        self.assertEqual(response.headers["content-type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.exported_rows(), [["word", "meaning"], ["apple", "사과"]])

    def test_empty_export_has_header(self):
        self.assertEqual(self.exported_rows(), [["word", "meaning"]])

    def test_export_keeps_creation_order_and_hides_deleted(self):
        self.add("zebra", "얼룩말")
        removed = self.add("mango", "망고")
        self.add("apple", "사과")
        self.client.post(DELETE_API, json={"ids": [removed["id"]]}, headers=self.headers)
        self.assertEqual([row[0] for row in self.exported_rows()[1:]], ["zebra", "apple"])

    def test_formula_values_are_neutralized(self):
        self.add("=HYPERLINK(1)", "+SUM(1)")
        self.add("@cmd", "-2+3")
        self.assertEqual(
            self.exported_rows()[1:],
            [["'=HYPERLINK(1)", "'+SUM(1)"], ["'@cmd", "'-2+3"]],
        )

    def test_round_trip_keeps_every_value(self):
        originals = {
            "=SUM(A1)": "수식/모양",
            "-ing": "-하는 중",
            "+plus": "@앞",
            "'=quoted": "'+따옴표",
            "'plain": "따옴표만",
            "it's": "쉼표, 있는 뜻",
            'say "hi"': '큰"따옴표',
        }
        for word, meaning in originals.items():
            self.add(word, meaning)
        exported = self.client.get(EXPORT_API).content
        items = self.listing()["items"]
        self.client.post(DELETE_API, json={"ids": [item["id"] for item in items]}, headers=self.headers)
        result = self.import_ok(exported)
        self.assertEqual(result["added"], len(originals))
        self.assertEqual(result["skipped_invalid"], 0)
        restored = {item["word"]: item["meaning"] for item in self.listing()["items"]}
        self.assertEqual(restored, originals)


class CsvGuardTest(unittest.TestCase):
    def test_neutralize_and_restore_are_inverse(self):
        values = ["apple", "=1", "+1", "-1", "@1", "\t1", "\r1", "'=1", "''=1", "'a", "", "'"]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(
                    csv_guard.restore_formula_prefix(csv_guard.neutralize_formula(value)), value
                )

    def test_plain_values_are_unchanged(self):
        for value in ("apple", "사과", "a=b", "'a"):
            self.assertEqual(csv_guard.neutralize_formula(value), value)

    def test_utf8_is_preferred_over_cp949(self):
        self.assertEqual(csv_guard.decode_upload("사과".encode("utf-8")), "사과")
        self.assertEqual(csv_guard.decode_upload("사과".encode("cp949")), "사과")
        self.assertEqual(csv_guard.decode_upload("﻿사과".encode("utf-8")), "사과")
        self.assertIsNone(csv_guard.decode_upload(b"\xff\xfe\x00\x81\xff"))


if __name__ == "__main__":
    unittest.main()

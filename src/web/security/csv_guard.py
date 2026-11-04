#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - CSV 수식 주입 방지와 업로드 파일 제한 (인증 설계 §5)
# 파일 위치: src/web/security/csv_guard.py

import re

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
# 앞에서부터 시도한다. CP949는 대부분의 바이트를 받아들이므로 UTF-8을 먼저 본다
UPLOAD_ENCODINGS = ("utf-8-sig", "cp949")

# 스프레드시트가 수식으로 해석하는 시작 글자. 앞에 ' 가 붙은 값도 왕복이 보존되게 함께 잡는다
_FORMULA_START = re.compile(r"^'*[=+\-@\t\r]")
_ESCAPED_FORMULA_START = re.compile(r"^'+[=+\-@\t\r]")


def neutralize_formula(value: str) -> str:
    """내보낼 값이 Excel에서 수식으로 실행되지 않도록 ' 를 붙인다."""
    return f"'{value}" if _FORMULA_START.match(value) else value


def restore_formula_prefix(value: str) -> str:
    """내보낸 파일을 다시 가져올 때 값이 바뀌지 않도록 붙였던 ' 를 뗀다."""
    return value[1:] if _ESCAPED_FORMULA_START.match(value) else value


def decode_upload(raw: bytes) -> str | None:
    """올라온 파일을 글자로 바꾼다. 어느 인코딩으로도 읽을 수 없으면 None을 돌려준다."""
    for encoding in UPLOAD_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None

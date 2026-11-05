#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 운영자가 올리는 단어장 파일의 크기 제한과 인코딩 해석 (인증 설계 §5)
# 파일 위치: src/web/security/csv_guard.py
#
# 회원의 CSV 내려받기를 없애면서 수식 주입 방지 함수를 지웠다. 이 파일을 쓰는 곳은 운영자 도구뿐이다.

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# 앞에서부터 시도한다. CP949는 대부분의 바이트를 받아들이므로 UTF-8을 먼저 본다
UPLOAD_ENCODINGS = ("utf-8-sig", "cp949")


def decode_upload(raw: bytes) -> str | None:
    """올라온 파일을 글자로 바꾼다. 어느 인코딩으로도 읽을 수 없으면 None을 돌려준다."""
    for encoding in UPLOAD_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None

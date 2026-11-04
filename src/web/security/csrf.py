#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 세션에서 CSRF 토큰을 파생하고 요청의 토큰을 검사한다
# 파일 위치: src/web/security/csrf.py

import hashlib
import hmac

from web.security.tokens import hash_token

CSRF_PURPOSE = b"smart-voca-csrf-v1"


def derive_csrf_token(session_token: str) -> str:
    # DB에는 해시만 있으므로 세션 값에서 다시 계산해 돌려준다. 세션 값을 모르면 만들 수 없다
    return hmac.new(session_token.encode("utf-8"), CSRF_PURPOSE, hashlib.sha256).hexdigest()


def is_valid_csrf_token(stored_hash: str, submitted_token: str | None) -> bool:
    if not submitted_token:
        return False
    # 앞에서부터 비교하면 일치한 길이가 응답 시간으로 드러나므로 일정 시간 비교를 쓴다
    return hmac.compare_digest(stored_hash, hash_token(submitted_token))

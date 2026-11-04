#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 세션·메일 토큰을 만들고 저장용 해시를 계산한다
# 파일 위치: src/web/security/tokens.py

import hashlib
import hmac
import secrets

TOKEN_BYTES = 32  # 256비트 (인증 설계 §2.1)


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    # 토큰은 충분히 무작위라 키 없는 해시로도 되돌릴 수 없다 (D-A02)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def keyed_hash(key: str, value: str) -> str:
    # 이메일과 IP는 경우의 수가 작아 서버 키가 있어야 DB 유출 시 되돌리지 못한다
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()

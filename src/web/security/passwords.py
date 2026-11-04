#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - argon2id 비밀번호 해시와 비밀번호 규칙 (인증 설계 §3.1, §3.2)
# 파일 위치: src/web/security/passwords.py

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from web.security.common_passwords import COMMON_PASSWORDS

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()
# 없는 계정도 같은 시간이 걸리게 이 해시로 검증한다. 응답 시간으로 가입 여부가 드러나지 않는다
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    has_real_hash = stored_hash is not None
    try:
        _hasher.verify(stored_hash if has_real_hash else _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return has_real_hash


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def find_password_problem(password: str, email: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"비밀번호는 {MAX_PASSWORD_LENGTH}자 이하여야 합니다."
    lowered = password.lower()
    if email and email in lowered:
        return "비밀번호에 이메일 주소를 넣을 수 없습니다."
    if lowered in COMMON_PASSWORDS:
        return "너무 흔한 비밀번호입니다. 다른 비밀번호를 입력해 주세요."
    return None

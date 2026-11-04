#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 가입에서 거절할 흔한 비밀번호 목록
# 파일 위치: src/web/security/common_passwords.py

# 직접 고른 대표 목록이다. 공개 전(M10)에 공개된 큰 목록으로 교체를 검토한다 (이슈 #9)
# 8자 미만은 길이 규칙에서 먼저 걸리므로 넣지 않는다
COMMON_PASSWORDS = frozenset(
    {
        "00000000", "11111111", "12121212", "12341234", "123123123", "12345678",
        "123456789", "1234567890", "1234qwer", "1q2w3e4r", "1q2w3e4r5t", "1qaz2wsx",
        "22222222", "55555555", "66666666", "77777777", "87654321", "88888888",
        "987654321", "99999999", "a1234567", "a12345678", "aa123456", "abc12345",
        "abcd1234", "abcdefgh", "admin123", "administrator", "adminadmin", "asdf1234",
        "asdfasdf", "asdfghjk", "asdfghjkl", "baseball", "changeme", "computer",
        "dragon123", "football", "iloveyou", "internet", "letmein1", "letmein123",
        "liverpool", "login123", "mustang1", "p@ssw0rd", "p@ssword", "pass1234",
        "passw0rd", "password", "password1", "password12", "password123", "password1234",
        "princess", "q1w2e3r4", "q1w2e3r4t5", "qazwsxedc", "qwe12345", "qwer1234",
        "qwerty12", "qwerty123", "qwerty1234", "qwertyui", "qwertyuiop", "samsung1",
        "samsung123", "sunshine", "superman", "test1234", "testtest", "trustno1",
        "welcome1", "welcome123", "whatever", "zaq12wsx", "zxcvbnm1", "zxcvbnm123",
    }
)

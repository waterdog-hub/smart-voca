#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - DB 기록으로 요청 횟수를 제한한다 (인증 설계 §5, D-A08)
# 파일 위치: src/web/security/rate_limit.py

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from web.errors import ApiError
from web.repositories import auth_repository

ACTION_LOGIN = "login"
ACTION_SIGNUP = "signup"
ACTION_RESEND_VERIFICATION = "resend_verification"
ACTION_PASSWORD_RESET = "password_reset"
ACTION_PASSWORD_CHECK = "password_check"


@dataclass(frozen=True)
class Limit:
    max_attempts: int
    window: timedelta


# 같은 계정이라도 실패가 많은 IP만 막아, 제3자가 피해자 계정을 잠그지 못하게 한다 (인증 설계 §5.1)
LOGIN_PER_ACCOUNT_AND_IP = Limit(5, timedelta(minutes=15))
LOGIN_PER_IP = Limit(50, timedelta(minutes=15))
# 가입과 재발송을 합쳐 세어 메일 폭탄과 제한 우회를 막는다
VERIFICATION_MAIL_PER_ACCOUNT = Limit(1, timedelta(minutes=1))
# 학교처럼 IP를 공유하는 곳을 고려해 IP 기준은 넉넉하게 둔다 (이슈 #9)
SIGNUP_PER_IP = Limit(20, timedelta(hours=1))
# 재설정 메일 폭탄을 막는다. 가입 여부와 상관없이 세므로 제한 응답으로 가입 여부가 드러나지 않는다 (D-M703)
PASSWORD_RESET_PER_ACCOUNT = Limit(3, timedelta(hours=1))
PASSWORD_RESET_PER_IP = Limit(20, timedelta(hours=1))
# 로그인한 세션이 탈취돼도 비밀번호 확인 값을 무차별 대입하지 못하게 한다 (D-M705)
PASSWORD_CHECK_PER_ACCOUNT = Limit(5, timedelta(minutes=15))


def enforce_limit(
    db: Session,
    limit: Limit,
    actions: tuple[str, ...],
    now: datetime,
    account_key_hash: str | None = None,
    ip_hash: str | None = None,
) -> None:
    # 최근 N번째 시도가 기간 안에 있으면 기간 안의 시도가 N번 이상이다
    nth_recent = auth_repository.nth_recent_attempt_time(
        db, actions, limit.max_attempts, account_key_hash, ip_hash
    )
    if nth_recent is None:
        return
    remaining = (nth_recent + limit.window - now).total_seconds()
    if remaining > 0:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
            retry_after=math.ceil(remaining),
        )

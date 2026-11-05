#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 비밀번호 재설정·변경, 표시 이름, 모든 기기 로그아웃, 탈퇴 규칙 (이슈 #18)
# 파일 위치: src/web/services/account_service.py

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from web.db.base import utc_now
from web.errors import ApiError
from web.repositories import auth_repository
from web.security import passwords, rate_limit
from web.security.tokens import generate_token, hash_token, keyed_hash
from web.services.auth_service import (
    EMAIL_PATTERN,
    MAX_EMAIL_LENGTH,
    CurrentSession,
    find_display_name_problem,
    normalize_email,
)
from web.services.mail_service import MailSendError, Mailer, build_password_reset_message
from web.settings import Settings

logger = logging.getLogger(__name__)

PURPOSE_RESET_PASSWORD = "reset_password"
RESET_PASSWORD_TTL = timedelta(minutes=30)  # 인증 설계 §3.5
WRONG_PASSWORD_MESSAGE = "현재 비밀번호가 올바르지 않습니다."
FIELDS_MESSAGE = "입력값을 확인해 주세요."


class AccountService:
    def __init__(self, db: Session, settings: Settings, mailer: Mailer, client_ip: str) -> None:
        self.db = db
        self.settings = settings
        self.mailer = mailer
        self.ip_hash = keyed_hash(settings.auth_hash_key, client_ip)

    def _account_key(self, email: str) -> str:
        return keyed_hash(self.settings.auth_hash_key, email)

    # ── 비밀번호 재설정 ────────────────────────────────────────────

    def request_password_reset(self, email: str) -> None:
        """가입 여부와 관계없이 같은 결과를 낸다 (D-A04). 제한도 가입 여부와 상관없이 센다."""
        email = normalize_email(email)
        if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
            raise ApiError(
                400,
                "VALIDATION_FAILED",
                FIELDS_MESSAGE,
                fields={"email": "올바른 이메일 주소를 입력해 주세요."},
            )
        now = utc_now()
        account_key = self._account_key(email)
        rate_limit.enforce_limit(
            self.db,
            rate_limit.PASSWORD_RESET_PER_ACCOUNT,
            (rate_limit.ACTION_PASSWORD_RESET,),
            now,
            account_key_hash=account_key,
        )
        rate_limit.enforce_limit(
            self.db,
            rate_limit.PASSWORD_RESET_PER_IP,
            (rate_limit.ACTION_PASSWORD_RESET,),
            now,
            ip_hash=self.ip_hash,
        )
        auth_repository.add_attempt(
            self.db, account_key, self.ip_hash, rate_limit.ACTION_PASSWORD_RESET, now
        )
        user = auth_repository.get_user_by_email(self.db, email)
        message = None
        if user is not None:
            token = generate_token()
            auth_repository.replace_mail_token(
                self.db,
                user.id,
                PURPOSE_RESET_PASSWORD,
                hash_token(token),
                now,
                now + RESET_PASSWORD_TTL,
            )
            message = build_password_reset_message(email, self.settings.public_base_url, token)
        self.db.commit()
        if message is None:
            logger.info("재설정 요청: 가입되지 않은 이메일")
            return
        try:
            self.mailer.send(message)
        except MailSendError:
            # 실패를 알리면 가입 여부가 드러나므로 로그에만 남긴다 (D-A04)
            logger.exception("재설정 메일 발송 실패")

    def confirm_password_reset(self, token: str, new_password: str) -> None:
        now = utc_now()
        user_id = auth_repository.consume_mail_token(
            self.db, hash_token(token), PURPOSE_RESET_PASSWORD, now
        )
        if user_id is None:
            self.db.rollback()
            raise ApiError(400, "TOKEN_INVALID", "링크가 만료되었거나 이미 사용되었습니다.")
        user = auth_repository.get_user_by_id(self.db, user_id)
        problem = passwords.find_password_problem(new_password, user.email)
        if problem:
            # 되돌리면 토큰 사용 표시도 취소되어, 같은 링크로 다시 시도할 수 있다
            self.db.rollback()
            raise ApiError(400, "VALIDATION_FAILED", FIELDS_MESSAGE, fields={"new_password": problem})
        user.password_hash = passwords.hash_password(new_password)
        # 메일을 받았으므로 이메일 인증도 끝난 것으로 본다 (D-M704)
        auth_repository.mark_email_verified(self.db, user.id, now)
        auth_repository.delete_all_sessions(self.db, user.id)
        # 잠금이 걸려 있던 본인이 곧바로 로그인할 수 있게 한다
        auth_repository.clear_attempts(
            self.db, self._account_key(user.email), rate_limit.ACTION_LOGIN
        )
        self.db.commit()
        logger.info("비밀번호 재설정: 회원 %s", user.id)

    # ── 로그인한 회원의 계정 관리 ──────────────────────────────────

    def _check_current_password(self, current: CurrentSession, password: str, now: datetime) -> None:
        """틀린 횟수를 세어 탈취된 세션의 무차별 대입을 막는다 (D-M705)."""
        user = current.user
        account_key = self._account_key(user.email)
        rate_limit.enforce_limit(
            self.db,
            rate_limit.PASSWORD_CHECK_PER_ACCOUNT,
            (rate_limit.ACTION_PASSWORD_CHECK,),
            now,
            account_key_hash=account_key,
        )
        if not passwords.verify_password(user.password_hash, password):
            auth_repository.add_attempt(
                self.db, account_key, self.ip_hash, rate_limit.ACTION_PASSWORD_CHECK, now
            )
            self.db.commit()
            raise ApiError(
                400,
                "VALIDATION_FAILED",
                FIELDS_MESSAGE,
                fields={"current_password": WRONG_PASSWORD_MESSAGE},
            )
        auth_repository.clear_attempts(self.db, account_key, rate_limit.ACTION_PASSWORD_CHECK)

    def change_password(
        self, current: CurrentSession, current_password: str, new_password: str
    ) -> None:
        user = current.user
        self._check_current_password(current, current_password, utc_now())
        problem = passwords.find_password_problem(new_password, user.email)
        if problem is None and new_password == current_password:
            problem = "현재 비밀번호와 다른 비밀번호를 입력해 주세요."
        if problem:
            self.db.commit()  # 확인 성공으로 지운 실패 기록을 확정한다
            raise ApiError(400, "VALIDATION_FAILED", FIELDS_MESSAGE, fields={"new_password": problem})
        user.password_hash = passwords.hash_password(new_password)
        auth_repository.delete_other_sessions(self.db, user.id, current.session.token_hash)
        self.db.commit()
        logger.info("비밀번호 변경: 회원 %s", user.id)

    def update_display_name(self, current: CurrentSession, display_name: str) -> None:
        display_name = display_name.strip()
        problem = find_display_name_problem(display_name)
        if problem:
            raise ApiError(400, "VALIDATION_FAILED", FIELDS_MESSAGE, fields={"display_name": problem})
        current.user.display_name = display_name
        self.db.commit()

    def logout_all(self, current: CurrentSession) -> None:
        auth_repository.delete_all_sessions(self.db, current.user.id)
        self.db.commit()
        logger.info("모든 기기 로그아웃: 회원 %s", current.user.id)

    def delete_account(self, current: CurrentSession, password: str) -> None:
        user_id = current.user.id
        self._check_current_password(current, password, utc_now())
        auth_repository.delete_user(self.db, user_id)
        self.db.commit()
        logger.info("탈퇴: 회원 %s", user_id)

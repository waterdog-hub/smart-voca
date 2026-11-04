#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 가입, 로그인, 세션, 이메일 인증 규칙 (인증 설계 §2, §3)
# 파일 위치: src/web/services/auth_service.py

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.db.base import utc_now
from web.db.tables import AuthSession, User
from web.errors import ApiError
from web.repositories import auth_repository
from web.security import passwords, rate_limit
from web.security.csrf import derive_csrf_token
from web.security.tokens import generate_token, hash_token, keyed_hash
from web.services.mail_service import (
    MailMessage,
    Mailer,
    MailSendError,
    build_already_registered_message,
    build_verification_message,
)
from web.settings import Settings

logger = logging.getLogger(__name__)

PURPOSE_VERIFY_EMAIL = "verify_email"
VERIFY_EMAIL_TTL = timedelta(hours=24)
ATTEMPT_RETENTION = timedelta(days=30)
# 만료 기준이 며칠 단위라 1분 오차는 문제없고, 요청마다 쓰는 부하를 줄인다 (이슈 #9)
LAST_SEEN_WRITE_INTERVAL = timedelta(minutes=1)
MAX_EMAIL_LENGTH = 254
MAX_DISPLAY_NAME_LENGTH = 100
# 형식만 간단히 본다. 실제로 받을 수 있는 주소인지는 인증 메일이 확인한다 (이슈 #9)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


@dataclass(frozen=True)
class LoginResult:
    user: User
    session_token: str
    csrf_token: str


@dataclass(frozen=True)
class CurrentSession:
    session: AuthSession
    user: User
    token: str

    @property
    def csrf_token(self) -> str:
        return derive_csrf_token(self.token)


def normalize_email(email: str) -> str:
    return email.strip().lower()  # 인증 설계 §3.3


def find_signup_problems(email: str, password: str, display_name: str) -> dict[str, str]:
    problems = {}
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        problems["email"] = "올바른 이메일 주소를 입력해 주세요."
    password_problem = passwords.find_password_problem(password, email)
    if password_problem:
        problems["password"] = password_problem
    if not display_name:
        problems["display_name"] = "표시 이름을 입력해 주세요."
    elif len(display_name) > MAX_DISPLAY_NAME_LENGTH:
        problems["display_name"] = f"표시 이름은 {MAX_DISPLAY_NAME_LENGTH}자 이하여야 합니다."
    elif not display_name.isprintable():
        problems["display_name"] = "표시 이름에 쓸 수 없는 문자가 있습니다."
    return problems


class AuthService:
    def __init__(self, db: Session, settings: Settings, mailer: Mailer, client_ip: str) -> None:
        self.db = db
        self.settings = settings
        self.mailer = mailer
        self.ip_hash = self._keyed_hash(client_ip)

    def _keyed_hash(self, value: str) -> str:
        return keyed_hash(self.settings.auth_hash_key, value)

    def _try_send(self, message: MailMessage) -> bool:
        try:
            self.mailer.send(message)
        except MailSendError:
            logger.exception("메일 발송 실패")
            return False
        return True

    def _issue_verification_mail(self, user_id: int, email: str, now: datetime) -> MailMessage:
        token = generate_token()
        auth_repository.replace_mail_token(
            self.db, user_id, PURPOSE_VERIFY_EMAIL, hash_token(token), now, now + VERIFY_EMAIL_TTL
        )
        return build_verification_message(email, self.settings.public_base_url, token)

    def _purge_expired(self, now: datetime) -> None:
        # 예약 작업 구조가 아직 없어 로그인과 가입 때 함께 정리한다 (이슈 #9)
        auth_repository.purge_expired(
            self.db,
            now,
            now - timedelta(days=self.settings.session_ttl_idle_days),
            now - ATTEMPT_RETENTION,
        )

    def signup(
        self,
        email: str,
        password: str,
        display_name: str,
        terms_agreed: bool,
        privacy_agreed: bool,
    ) -> None:
        email = normalize_email(email)
        display_name = display_name.strip()
        problems = find_signup_problems(email, password, display_name)
        if not terms_agreed:
            problems["terms_agreed"] = "이용약관에 동의해 주세요."
        if not privacy_agreed:
            problems["privacy_agreed"] = "개인정보 처리방침에 동의해 주세요."
        if problems:
            raise ApiError(400, "VALIDATION_FAILED", "입력값을 확인해 주세요.", fields=problems)

        now = utc_now()
        account_key = self._keyed_hash(email)
        rate_limit.enforce_limit(
            self.db,
            rate_limit.VERIFICATION_MAIL_PER_ACCOUNT,
            (rate_limit.ACTION_SIGNUP, rate_limit.ACTION_RESEND_VERIFICATION),
            now,
            account_key_hash=account_key,
        )
        rate_limit.enforce_limit(
            self.db,
            rate_limit.SIGNUP_PER_IP,
            (rate_limit.ACTION_SIGNUP,),
            now,
            ip_hash=self.ip_hash,
        )
        auth_repository.add_attempt(self.db, account_key, self.ip_hash, rate_limit.ACTION_SIGNUP, now)
        self._purge_expired(now)
        self.db.commit()

        # 중복 여부와 상관없이 해시와 메일 처리를 모두 거쳐 응답 시간으로 가입 여부가 드러나지 않게 한다
        password_hash = passwords.hash_password(password)
        message = self._create_account_or_notice(email, password_hash, display_name, now)
        # 메일 실패를 응답으로 알리면 신규와 중복의 차이가 생길 수 있어 로그에만 남긴다 (D-A04)
        self._try_send(message)

    def _create_account_or_notice(
        self, email: str, password_hash: str, display_name: str, now: datetime
    ) -> MailMessage:
        notice = build_already_registered_message(email, self.settings.public_base_url)
        if auth_repository.get_user_by_email(self.db, email) is not None:
            logger.info("가입 요청: 이미 가입된 이메일")
            return notice
        try:
            user = auth_repository.add_user_with_settings(
                self.db, email, password_hash, display_name, now
            )
            message = self._issue_verification_mail(user.id, email, now)
            self.db.commit()
        except IntegrityError:
            # 같은 이메일의 가입이 동시에 들어오면 유일 제약이 한쪽을 막는다
            self.db.rollback()
            return notice
        logger.info("가입 완료: 회원 %s", user.id)
        return message

    def login(self, email: str, password: str, previous_session_token: str | None) -> LoginResult:
        email = normalize_email(email)
        now = utc_now()
        account_key = self._keyed_hash(email)
        rate_limit.enforce_limit(
            self.db,
            rate_limit.LOGIN_PER_ACCOUNT_AND_IP,
            (rate_limit.ACTION_LOGIN,),
            now,
            account_key_hash=account_key,
            ip_hash=self.ip_hash,
        )
        rate_limit.enforce_limit(
            self.db, rate_limit.LOGIN_PER_IP, (rate_limit.ACTION_LOGIN,), now, ip_hash=self.ip_hash
        )

        user = auth_repository.get_user_by_email(self.db, email)
        stored_hash = user.password_hash if user is not None else None
        # 없는 이메일과 소셜 전용 계정도 같은 검증 시간을 쓰고 같은 오류를 준다 (API 설계 §2.1)
        if not passwords.verify_password(stored_hash, password):
            auth_repository.add_attempt(
                self.db, account_key, self.ip_hash, rate_limit.ACTION_LOGIN, now
            )
            self.db.commit()
            logger.info("로그인 실패: 계정 %s", account_key[:12])
            raise ApiError(401, "LOGIN_FAILED", "이메일 또는 비밀번호가 올바르지 않습니다.")

        if passwords.needs_rehash(stored_hash):
            user.password_hash = passwords.hash_password(password)
        auth_repository.clear_attempts(self.db, account_key, rate_limit.ACTION_LOGIN)
        # 로그인 전 세션을 이어 쓰지 않아 세션 고정 공격을 막는다 (인증 설계 §2.1)
        if previous_session_token:
            auth_repository.delete_session_by_hash(self.db, hash_token(previous_session_token))
        session_token = generate_token()
        csrf_token = derive_csrf_token(session_token)
        auth_repository.add_login_session(
            self.db,
            user.id,
            hash_token(session_token),
            hash_token(csrf_token),
            now,
            now + timedelta(days=self.settings.session_ttl_absolute_days),
        )
        self._purge_expired(now)
        self.db.commit()
        logger.info("로그인 성공: 회원 %s", user.id)
        return LoginResult(user=user, session_token=session_token, csrf_token=csrf_token)

    def find_current_session(self, session_token: str | None) -> CurrentSession | None:
        if not session_token:
            return None
        token_hash = hash_token(session_token)
        found = auth_repository.get_login_session(self.db, token_hash)
        if found is None:
            return None
        session, user = found
        now = utc_now()
        idle_limit = timedelta(days=self.settings.session_ttl_idle_days)
        if now >= session.expires_at or now >= session.last_seen_at + idle_limit:
            auth_repository.delete_session_by_hash(self.db, token_hash)
            self.db.commit()
            return None
        if now - session.last_seen_at >= LAST_SEEN_WRITE_INTERVAL:
            session.last_seen_at = now
            self.db.commit()
        return CurrentSession(session=session, user=user, token=session_token)

    def logout(self, current: CurrentSession) -> None:
        auth_repository.delete_session_by_hash(self.db, current.session.token_hash)
        self.db.commit()
        logger.info("로그아웃: 회원 %s", current.user.id)

    def verify_email(self, token: str) -> None:
        now = utc_now()
        user_id = auth_repository.consume_mail_token(
            self.db, hash_token(token), PURPOSE_VERIFY_EMAIL, now
        )
        if user_id is None:
            self.db.rollback()
            raise ApiError(400, "TOKEN_INVALID", "링크가 만료되었거나 이미 사용되었습니다.")
        auth_repository.mark_email_verified(self.db, user_id, now)
        self.db.commit()
        logger.info("이메일 인증 완료: 회원 %s", user_id)

    def resend_verification(self, user: User) -> None:
        if user.email_verified_at is not None:
            return
        now = utc_now()
        account_key = self._keyed_hash(user.email)
        rate_limit.enforce_limit(
            self.db,
            rate_limit.VERIFICATION_MAIL_PER_ACCOUNT,
            (rate_limit.ACTION_SIGNUP, rate_limit.ACTION_RESEND_VERIFICATION),
            now,
            account_key_hash=account_key,
        )
        auth_repository.add_attempt(
            self.db, account_key, self.ip_hash, rate_limit.ACTION_RESEND_VERIFICATION, now
        )
        message = self._issue_verification_mail(user.id, user.email, now)
        self.db.commit()
        if not self._try_send(message):
            # 로그인한 본인의 요청이라 실패를 알려도 다른 사람의 가입 여부가 드러나지 않는다
            raise ApiError(
                503, "MAIL_SEND_FAILED", "메일 발송에 실패했습니다. 잠시 후 다시 시도해 주세요."
            )

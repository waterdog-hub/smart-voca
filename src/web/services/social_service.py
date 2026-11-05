#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 소셜 로그인 흐름: 시작, 콜백, 계정 연결 규칙, 이메일 없는 가입, 연결 해제 (이슈 #19)
# 파일 위치: src/web/services/social_service.py

import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.db.base import utc_now
from web.db.tables import AuthSession, User
from web.errors import ApiError
from web.repositories import auth_repository, social_repository
from web.security import rate_limit
from web.security.csrf import derive_csrf_token
from web.security.tokens import generate_token, hash_token, keyed_hash
from web.services.auth_service import (
    EMAIL_PATTERN,
    MAX_EMAIL_LENGTH,
    find_display_name_problem,
    normalize_email,
)
from web.services.mail_service import (
    Mailer,
    MailSendError,
    build_already_registered_message,
    build_verification_message,
)
from web.services.social_providers import (
    PROVIDER_NAMES,
    ProviderProfile,
    SocialAuthError,
    SocialProvider,
    pkce_challenge,
)
from web.settings import Settings

logger = logging.getLogger(__name__)

OAUTH_START_TTL = timedelta(minutes=10)  # 인증 설계 §4.5
PENDING_SIGNUP_TTL = timedelta(hours=24)  # 데이터 모델 §4.3
DEFAULT_DISPLAY_NAME = "회원"
CALLBACK_PATH = "/api/v1/auth/social/{provider}/callback"

# 콜백 실패는 주소의 짧은 코드로 화면에 알린다. 화면이 코드별 문구를 가진다 (pages.py)
ERROR_STATE = "state"
ERROR_DENIED = "denied"
ERROR_PROVIDER = "provider"
ERROR_TAKEN = "taken"
ERROR_BUSY = "busy"
ERROR_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CallbackResult:
    redirect: str
    session_token: str | None = None  # 있으면 로그인 쿠키를 발급한다
    keep_pending_cookie: bool = False  # 이메일 입력 단계로 가면 대기 쿠키를 유지한다


@dataclass(frozen=True)
class StartResult:
    authorize_url: str
    pending_token: str


def _failure(error: str, linking: bool) -> CallbackResult:
    base = "/account" if linking else "/login"
    return CallbackResult(f"{base}?social_error={error}")


class SocialService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        providers: dict[str, SocialProvider],
        mailer: Mailer,
        client_ip: str,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers
        self.mailer = mailer
        self.ip_hash = keyed_hash(settings.auth_hash_key, client_ip)

    # ── 시작 ──────────────────────────────────────────────────

    def available_providers(self) -> list[str]:
        return [name for name in PROVIDER_NAMES if name in self.providers]

    def _provider(self, name: str) -> SocialProvider:
        provider = self.providers.get(name)
        if provider is None:
            raise ApiError(404, "SOCIAL_NOT_AVAILABLE", "사용할 수 없는 로그인 방식입니다.")
        return provider

    def start(self, provider_name: str, link_user_id: int | None = None) -> StartResult:
        provider = self._provider(provider_name)
        now = utc_now()
        # 시작 요청은 DB 행을 만들므로 IP당 횟수를 제한한다
        rate_limit.enforce_limit(
            self.db,
            rate_limit.SOCIAL_START_PER_IP,
            (rate_limit.ACTION_SOCIAL_START,),
            now,
            ip_hash=self.ip_hash,
        )
        auth_repository.add_attempt(
            self.db, self.ip_hash, self.ip_hash, rate_limit.ACTION_SOCIAL_START, now
        )
        state = generate_token()
        code_verifier = secrets.token_urlsafe(48)  # 64자, PKCE 규격은 43~128자 (RFC 7636)
        pending_token = generate_token()
        social_repository.add_oauth_start(
            self.db,
            hash_token(pending_token),
            hash_token(derive_csrf_token(pending_token)),
            provider_name,
            state,
            code_verifier,
            link_user_id,
            now,
            now + OAUTH_START_TTL,
        )
        # 예약 작업이 없어 시작할 때 만료된 대기 행과 오래된 기록을 정리한다 (이슈 #9와 같은 방식)
        auth_repository.purge_expired(
            self.db,
            now,
            now - timedelta(days=self.settings.session_ttl_idle_days),
            now - timedelta(days=30),
        )
        self.db.commit()
        url = provider.authorize_url(self._redirect_uri(provider_name), state, pkce_challenge(code_verifier))
        return StartResult(url, pending_token)

    def _redirect_uri(self, provider_name: str) -> str:
        return self.settings.public_base_url + CALLBACK_PATH.format(provider=provider_name)

    # ── 콜백 ──────────────────────────────────────────────────

    def handle_callback(
        self,
        provider_name: str,
        code: str | None,
        state: str | None,
        provider_error: str | None,
        pending_token: str | None,
        previous_session_token: str | None,
    ) -> CallbackResult:
        provider = self.providers.get(provider_name)
        if provider is None or not pending_token:
            return _failure(ERROR_STATE if provider else ERROR_UNAVAILABLE, linking=False)
        now = utc_now()
        row = social_repository.get_pending_row(self.db, hash_token(pending_token))
        if (
            row is None
            or row.pending_provider != provider_name
            or row.oauth_state is None
            or now >= row.expires_at
        ):
            if row is not None:
                social_repository.delete_row(self.db, row.id)
                self.db.commit()
            return _failure(ERROR_STATE, linking=False)
        linking = row.oauth_link_user_id is not None
        link_user_id = row.oauth_link_user_id
        code_verifier = row.oauth_code_verifier
        row_id = row.id
        state_matches = bool(state) and hmac.compare_digest(row.oauth_state, state)
        # 일치하면 state를 바로 지워 같은 콜백을 두 번 처리하지 못하게 한다
        if not state_matches or not social_repository.consume_oauth_state(self.db, row_id, state):
            # 틀린 state는 시도 한 번으로 끝내 값을 맞춰 보는 길을 막는다
            self.db.rollback()
            social_repository.delete_row(self.db, row_id)
            self.db.commit()
            return _failure(ERROR_STATE, linking)
        self.db.commit()

        if provider_error or not code:
            return self._finish_failure(row_id, ERROR_DENIED, linking)
        try:
            profile = provider.fetch_profile(self._redirect_uri(provider_name), code, code_verifier)
        except SocialAuthError:
            return self._finish_failure(row_id, ERROR_PROVIDER, linking)

        try:
            if linking:
                return self._link_account(row_id, link_user_id, provider_name, profile, now)
            return self._login_or_sign_up(row_id, provider_name, profile, previous_session_token, now)
        except IntegrityError:
            # 같은 소셜 계정이나 이메일의 처리가 동시에 들어오면 유일 제약이 한쪽을 막는다
            self.db.rollback()
            return self._finish_failure(row_id, ERROR_BUSY, linking)

    def _finish_failure(self, row_id: int, error: str, linking: bool) -> CallbackResult:
        social_repository.delete_row(self.db, row_id)
        self.db.commit()
        return _failure(error, linking)

    def _link_account(
        self, row_id: int, user_id: int, provider_name: str, profile: ProviderProfile, now
    ) -> CallbackResult:
        user = auth_repository.get_user_by_id(self.db, user_id)
        existing = social_repository.get_account_with_user(self.db, provider_name, profile.provider_user_id)
        social_repository.delete_row(self.db, row_id)
        if user is None:
            self.db.commit()
            return _failure(ERROR_STATE, linking=True)
        if existing is not None and existing[1].id != user.id:
            self.db.commit()
            return _failure(ERROR_TAKEN, linking=True)
        if existing is None:
            # 같은 제공자의 다른 계정이 이미 붙어 있으면 유일 제약이 막는다 (회원당 제공자 하나)
            if provider_name in social_repository.list_providers(self.db, user.id):
                self.db.commit()
                return _failure(ERROR_TAKEN, linking=True)
            social_repository.add_account(
                self.db, user.id, provider_name, profile.provider_user_id, profile.email, now
            )
        self.db.commit()
        logger.info("소셜 계정 연결: 회원 %s, %s", user.id, provider_name)
        return CallbackResult("/account?social=linked")

    def _login_or_sign_up(
        self,
        row_id: int,
        provider_name: str,
        profile: ProviderProfile,
        previous_session_token: str | None,
        now,
    ) -> CallbackResult:
        found = social_repository.get_account_with_user(self.db, provider_name, profile.provider_user_id)
        if found is not None:
            return self._login(row_id, found[1], previous_session_token, now)

        if profile.email and profile.email_verified:
            user = auth_repository.get_user_by_email(self.db, profile.email)
            if user is not None:
                if user.email_verified_at is None:
                    # 남의 이메일로 먼저 가입해 둔 공격자가 비밀번호를 쥔 채 계정이 넘어오지 않게 한다 (D-M805)
                    user.password_hash = None
                    auth_repository.delete_all_sessions(self.db, user.id)
                    auth_repository.mark_email_verified(self.db, user.id, now)
                    logger.info("미인증 계정을 소셜 인증으로 인수: 회원 %s", user.id)
            else:
                user = auth_repository.add_user_with_settings(
                    self.db, profile.email, None, self._display_name(profile), now
                )
                user.email_verified_at = now
            social_repository.add_account(
                self.db, user.id, provider_name, profile.provider_user_id, profile.email, now
            )
            return self._login(row_id, user, previous_session_token, now)

        # 이메일이 없거나 인증되지 않았다: 이메일을 입력받아 인증한 뒤 가입시킨다 (D-M806)
        row = self.db.get(AuthSession, row_id)
        row.pending_provider_user_id = profile.provider_user_id
        row.pending_display_name = self._display_name(profile)
        row.pending_email = None
        row.expires_at = now + PENDING_SIGNUP_TTL
        self.db.commit()
        return CallbackResult("/signup/social", keep_pending_cookie=True)

    def _display_name(self, profile: ProviderProfile) -> str:
        candidates = (profile.display_name, profile.email.split("@")[0] if profile.email else None)
        for candidate in candidates:
            if candidate:
                name = candidate.strip()[:100]
                if find_display_name_problem(name) is None:
                    return name
        return DEFAULT_DISPLAY_NAME

    def _login(self, row_id: int, user: User, previous_session_token: str | None, now) -> CallbackResult:
        social_repository.delete_row(self.db, row_id)
        # 로그인 전 세션을 이어 쓰지 않아 세션 고정 공격을 막는다 (인증 설계 §2.1)
        if previous_session_token:
            auth_repository.delete_session_by_hash(self.db, hash_token(previous_session_token))
        session_token = generate_token()
        auth_repository.add_login_session(
            self.db,
            user.id,
            hash_token(session_token),
            hash_token(derive_csrf_token(session_token)),
            now,
            now + timedelta(days=self.settings.session_ttl_absolute_days),
        )
        self.db.commit()
        logger.info("소셜 로그인: 회원 %s", user.id)
        return CallbackResult("/", session_token=session_token)

    # ── 이메일 없는 소셜 가입 ──────────────────────────────────

    def get_pending_signup(self, pending_token: str | None) -> AuthSession | None:
        """이메일 입력 단계에 있는 가입 대기 행. 없거나 만료되면 None."""
        if not pending_token:
            return None
        row = social_repository.get_pending_row(self.db, hash_token(pending_token))
        if row is None or row.pending_provider_user_id is None or utc_now() >= row.expires_at:
            return None
        return row

    def request_signup_mail(self, pending_token: str | None, email: str) -> None:
        row = self.get_pending_signup(pending_token)
        if row is None:
            raise ApiError(401, "SIGNUP_EXPIRED", "가입 시간이 지났습니다. 소셜 로그인을 다시 시작해 주세요.")
        email = normalize_email(email)
        if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
            raise ApiError(
                400,
                "VALIDATION_FAILED",
                "입력값을 확인해 주세요.",
                fields={"email": "올바른 이메일 주소를 입력해 주세요."},
            )
        now = utc_now()
        account_key = keyed_hash(self.settings.auth_hash_key, email)
        rate_limit.enforce_limit(
            self.db,
            rate_limit.VERIFICATION_MAIL_PER_ACCOUNT,
            (rate_limit.ACTION_SIGNUP, rate_limit.ACTION_RESEND_VERIFICATION),
            now,
            account_key_hash=account_key,
        )
        rate_limit.enforce_limit(
            self.db, rate_limit.SIGNUP_PER_IP, (rate_limit.ACTION_SIGNUP,), now, ip_hash=self.ip_hash
        )
        auth_repository.add_attempt(self.db, account_key, self.ip_hash, rate_limit.ACTION_SIGNUP, now)
        if auth_repository.get_user_by_email(self.db, email) is not None:
            # 이미 가입된 이메일은 토큰 없이 안내만 보낸다. 응답은 같다 (D-A04)
            self.db.commit()
            message = build_already_registered_message(email, self.settings.public_base_url)
        else:
            token = generate_token()
            row.pending_email = email
            row.pending_token_hash = hash_token(token)
            row.expires_at = now + PENDING_SIGNUP_TTL
            self.db.commit()
            message = build_verification_message(email, self.settings.public_base_url, token)
        try:
            self.mailer.send(message)
        except MailSendError:
            # 실패를 알리면 가입 여부가 드러날 수 있어 로그에만 남긴다 (D-A04)
            logger.exception("소셜 가입 메일 발송 실패")

    def complete_signup_from_token(self, token: str) -> bool:
        """이메일 인증 링크가 소셜 가입 대기의 것이면 회원을 만든다. 해당하지 않으면 False."""
        now = utc_now()
        row = social_repository.find_row_by_signup_token(self.db, hash_token(token), now)
        if row is None:
            return False
        provider_name = row.pending_provider
        provider_user_id = row.pending_provider_user_id
        email = row.pending_email
        display_name = row.pending_display_name or DEFAULT_DISPLAY_NAME
        if not social_repository.delete_row_returning(self.db, row.id):
            self.db.rollback()
            raise ApiError(400, "TOKEN_INVALID", "링크가 만료되었거나 이미 사용되었습니다.")
        if auth_repository.get_user_by_email(self.db, email) is not None:
            # 인증 메일을 보낸 뒤 같은 이메일로 가입되었다. 소셜 계정을 남의 계정에 자동으로 붙이지 않는다
            self.db.commit()
            raise ApiError(400, "TOKEN_INVALID", "링크가 만료되었거나 이미 사용되었습니다.")
        try:
            user = auth_repository.add_user_with_settings(self.db, email, None, display_name, now)
            user.email_verified_at = now
            social_repository.add_account(self.db, user.id, provider_name, provider_user_id, email, now)
            self.db.commit()
        except IntegrityError:
            # 동시에 가입되었거나 같은 소셜 계정이 먼저 연결됐다
            self.db.rollback()
            raise ApiError(400, "TOKEN_INVALID", "링크가 만료되었거나 이미 사용되었습니다.")
        logger.info("소셜 가입 완료: 회원 %s, %s", user.id, provider_name)
        return True

    # ── 연결 해제 ─────────────────────────────────────────────

    def unlink(self, user: User, provider_name: str) -> None:
        if provider_name not in PROVIDER_NAMES:
            raise ApiError(404, "SOCIAL_NOT_AVAILABLE", "사용할 수 없는 로그인 방식입니다.")
        linked = social_repository.list_providers(self.db, user.id)
        if provider_name not in linked:
            return
        if user.password_hash is None and len(linked) <= 1:
            raise ApiError(
                409,
                "LAST_LOGIN_METHOD",
                "마지막 로그인 수단은 해제할 수 없습니다. 먼저 비밀번호를 설정해 주세요.",
            )
        social_repository.delete_account(self.db, user.id, provider_name)
        self.db.commit()
        logger.info("소셜 계정 해제: 회원 %s, %s", user.id, provider_name)

    def linked_providers(self, user: User) -> list[str]:
        return social_repository.list_providers(self.db, user.id)

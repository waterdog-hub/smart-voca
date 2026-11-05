#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 구글·카카오 OAuth 어댑터: 인증 주소 만들기와 코드 → 사용자 정보 교환 (이슈 #19)
# 파일 위치: src/web/services/social_providers.py
#
# 실제 제공자에는 아직 앱을 등록하지 않아 호출은 모의 전송(httpx.MockTransport)으로만 확인했다.
# 응답 형식은 제공자 공식 문서 기준이며, 등록 뒤 실제 로그인으로 확인해야 한다 (이슈 #19 알려진 위험).

import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from web.settings import Settings

logger = logging.getLogger(__name__)

GOOGLE = "google"
KAKAO = "kakao"
PROVIDER_NAMES = (GOOGLE, KAKAO)
PROVIDER_LABELS = {GOOGLE: "Google", KAKAO: "카카오"}
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_PROVIDER_USER_ID_LENGTH = 255


class SocialAuthError(Exception):
    """제공자와의 교환이 실패했다. 제공자 응답 내용은 로그에도 남기지 않는다."""


@dataclass(frozen=True)
class ProviderProfile:
    provider_user_id: str
    email: str | None  # 소문자로 정리된 값. 제공자가 주지 않으면 None
    email_verified: bool
    display_name: str | None


class SocialProvider(Protocol):
    name: str

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str) -> str: ...

    def fetch_profile(self, redirect_uri: str, code: str, code_verifier: str) -> ProviderProfile: ...


def pkce_challenge(code_verifier: str) -> str:
    """PKCE S256: verifier의 SHA-256을 padding 없는 base64url로 만든다 (RFC 7636)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _clean_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    return email or None


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text and text.isprintable() else None


class _OAuthProvider:
    """공통 흐름: 코드로 액세스 토큰을 받고 그 토큰으로 사용자 정보를 읽는다."""

    name: str
    authorize_endpoint: str
    token_endpoint: str
    profile_endpoint: str
    scope: str

    def __init__(
        self, client_id: str, client_secret: str | None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.transport = transport

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.authorize_endpoint}?{urlencode(query)}"

    def _token_form(self, redirect_uri: str, code: str, code_verifier: str) -> dict[str, str]:
        form = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }
        if self.client_secret:
            form["client_secret"] = self.client_secret
        return form

    def fetch_profile(self, redirect_uri: str, code: str, code_verifier: str) -> ProviderProfile:
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, transport=self.transport) as client:
                token_response = client.post(
                    self.token_endpoint, data=self._token_form(redirect_uri, code, code_verifier)
                )
                token_response.raise_for_status()
                access_token = token_response.json().get("access_token")
                if not isinstance(access_token, str) or not access_token:
                    raise SocialAuthError("액세스 토큰이 없습니다.")
                profile_response = client.get(
                    self.profile_endpoint, headers={"Authorization": f"Bearer {access_token}"}
                )
                profile_response.raise_for_status()
                return self.parse_profile(profile_response.json())
        except (httpx.HTTPError, ValueError) as error:
            # 응답 본문에는 코드나 토큰이 들어 있을 수 있어 종류만 남긴다
            logger.warning("%s 연동 실패: %s", self.name, type(error).__name__)
            raise SocialAuthError("제공자 응답을 처리하지 못했습니다.") from error

    def parse_profile(self, data: object) -> ProviderProfile:
        raise NotImplementedError


class GoogleProvider(_OAuthProvider):
    name = GOOGLE
    authorize_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    profile_endpoint = "https://openidconnect.googleapis.com/v1/userinfo"
    scope = "openid email profile"

    def parse_profile(self, data: object) -> ProviderProfile:
        if not isinstance(data, dict):
            raise SocialAuthError("사용자 정보 형식이 올바르지 않습니다.")
        subject = data.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > MAX_PROVIDER_USER_ID_LENGTH:
            raise SocialAuthError("사용자 번호가 없습니다.")
        email = _clean_email(data.get("email"))
        # 구글은 email_verified를 불리언으로 준다. 값이 불리언이 아니면 인증되지 않은 것으로 본다
        verified = data.get("email_verified") is True
        return ProviderProfile(subject, email, bool(email) and verified, _clean_text(data.get("name")))


class KakaoProvider(_OAuthProvider):
    name = KAKAO
    authorize_endpoint = "https://kauth.kakao.com/oauth/authorize"
    token_endpoint = "https://kauth.kakao.com/oauth/token"
    profile_endpoint = "https://kapi.kakao.com/v2/user/me"
    scope = "account_email profile_nickname"

    def parse_profile(self, data: object) -> ProviderProfile:
        if not isinstance(data, dict):
            raise SocialAuthError("사용자 정보 형식이 올바르지 않습니다.")
        raw_id = data.get("id")
        # 카카오 회원 번호는 정수다. 불리언은 정수의 하위 형식이라 따로 거른다
        if isinstance(raw_id, bool) or not isinstance(raw_id, int):
            raise SocialAuthError("사용자 번호가 없습니다.")
        account = data.get("kakao_account")
        account = account if isinstance(account, dict) else {}
        email = _clean_email(account.get("email"))
        # 카카오의 이메일 인증 기준은 공식 문서로 확인하지 못했다 (인증 설계 §4.3).
        # 보수적으로 유효하고 인증된 이메일이 모두 참일 때만 인증된 것으로 본다
        verified = account.get("is_email_valid") is True and account.get("is_email_verified") is True
        profile = account.get("profile")
        nickname = _clean_text(profile.get("nickname")) if isinstance(profile, dict) else None
        return ProviderProfile(str(raw_id), email, bool(email) and verified, nickname)


def create_social_providers(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> dict[str, SocialProvider]:
    """키가 있는 제공자만 켠다. 시연 환경에서는 켜지 않는다 (콜백 주소를 등록할 수 없다, D-M802)."""
    if settings.auto_verifies_email:
        return {}
    providers: dict[str, SocialProvider] = {}
    if settings.google_client_id and settings.google_client_secret:
        providers[GOOGLE] = GoogleProvider(
            settings.google_client_id, settings.google_client_secret, transport
        )
    if settings.kakao_rest_api_key:
        providers[KAKAO] = KakaoProvider(
            settings.kakao_rest_api_key, settings.kakao_client_secret, transport
        )
    return providers

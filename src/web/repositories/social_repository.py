#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 소셜 계정 연결과 소셜 로그인 대기 행의 DB 읽기와 쓰기 (이슈 #19)
# 파일 위치: src/web/repositories/social_repository.py

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from web.db.tables import AuthSession, SocialAccount, User


def get_account_with_user(
    db: Session, provider: str, provider_user_id: str
) -> tuple[SocialAccount, User] | None:
    row = db.execute(
        select(SocialAccount, User)
        .join(User, SocialAccount.user_id == User.id)
        .where(
            SocialAccount.provider == provider,
            SocialAccount.provider_user_id == provider_user_id,
        )
    ).first()
    return None if row is None else (row[0], row[1])


def list_providers(db: Session, user_id: int) -> list[str]:
    return list(
        db.scalars(
            select(SocialAccount.provider)
            .where(SocialAccount.user_id == user_id)
            .order_by(SocialAccount.provider)
        )
    )


def count_accounts(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count()).select_from(SocialAccount).where(SocialAccount.user_id == user_id))


def add_account(
    db: Session, user_id: int, provider: str, provider_user_id: str, email: str | None, now: datetime
) -> None:
    db.add(
        SocialAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email_at_link=email,
            created_at=now,
        )
    )


def delete_account(db: Session, user_id: int, provider: str) -> bool:
    result = db.execute(
        delete(SocialAccount).where(
            SocialAccount.user_id == user_id, SocialAccount.provider == provider
        )
    )
    return result.rowcount > 0


def add_oauth_start(
    db: Session,
    token_hash: str,
    csrf_token_hash: str,
    provider: str,
    state: str,
    code_verifier: str,
    link_user_id: int | None,
    now: datetime,
    expires_at: datetime,
) -> None:
    db.add(
        AuthSession(
            user_id=None,
            token_hash=token_hash,
            csrf_token_hash=csrf_token_hash,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            pending_provider=provider,
            oauth_state=state,
            oauth_code_verifier=code_verifier,
            oauth_link_user_id=link_user_id,
        )
    )


def get_pending_row(db: Session, token_hash: str) -> AuthSession | None:
    return db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash, AuthSession.user_id.is_(None)
        )
    )


def consume_oauth_state(db: Session, row_id: int, state: str) -> bool:
    # 조건부 갱신 한 문장이라 같은 state의 콜백이 동시에 와도 한 요청만 성공한다 (인증 설계 §4.5)
    updated = db.scalar(
        update(AuthSession)
        .where(AuthSession.id == row_id, AuthSession.oauth_state == state)
        .values(oauth_state=None, oauth_code_verifier=None)
        .returning(AuthSession.id)
    )
    return updated is not None


def delete_row(db: Session, row_id: int) -> None:
    db.execute(delete(AuthSession).where(AuthSession.id == row_id))


def find_row_by_signup_token(db: Session, token_hash: str, now: datetime) -> AuthSession | None:
    return db.scalar(
        select(AuthSession).where(
            AuthSession.pending_token_hash == token_hash,
            AuthSession.user_id.is_(None),
            AuthSession.expires_at > now,
        )
    )


def delete_row_returning(db: Session, row_id: int) -> bool:
    # 같은 인증 링크를 동시에 눌러도 한 요청만 행을 지워 회원을 만든다
    deleted = db.scalar(
        delete(AuthSession).where(AuthSession.id == row_id).returning(AuthSession.id)
    )
    return deleted is not None

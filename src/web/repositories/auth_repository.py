#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 회원, 세션, 메일 토큰, 시도 기록의 DB 읽기와 쓰기
# 파일 위치: src/web/repositories/auth_repository.py

from datetime import datetime

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from web.db.tables import AuthSession, AuthToken, LoginAttempt, User, UserSetting


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def add_user_with_settings(
    db: Session, email: str, password_hash: str, display_name: str, now: datetime
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        display_name=display_name,
        terms_agreed_at=now,
        privacy_agreed_at=now,
        created_at=now,
    )
    db.add(user)
    db.flush()
    # 설정 API는 회원마다 행이 있다고 가정하므로 가입과 같은 트랜잭션에서 만든다 (API 설계 §4)
    db.add(UserSetting(user_id=user.id))
    return user


def mark_email_verified(db: Session, user_id: int, now: datetime) -> None:
    db.execute(
        update(User)
        .where(User.id == user_id, User.email_verified_at.is_(None))
        .values(email_verified_at=now)
    )


def add_login_session(
    db: Session,
    user_id: int,
    token_hash: str,
    csrf_token_hash: str,
    now: datetime,
    expires_at: datetime,
) -> None:
    db.add(
        AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            csrf_token_hash=csrf_token_hash,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
        )
    )


def get_login_session(db: Session, token_hash: str) -> tuple[AuthSession, User] | None:
    # 내부 조인이라 회원이 없는 가입 대기 세션은 로그인 세션으로 인정되지 않는다
    row = db.execute(
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == token_hash)
    ).first()
    return None if row is None else (row[0], row[1])


def delete_session_by_hash(db: Session, token_hash: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))


def replace_mail_token(
    db: Session, user_id: int, purpose: str, token_hash: str, now: datetime, expires_at: datetime
) -> None:
    # 같은 용도의 안 쓴 토큰은 무효로 한다 (인증 설계 §3.5)
    db.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
    )
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
        )
    )


def consume_mail_token(db: Session, token_hash: str, purpose: str, now: datetime) -> int | None:
    # 조건부 갱신 한 문장이라 같은 링크를 동시에 눌러도 한 요청만 성공한다
    return db.scalar(
        update(AuthToken)
        .where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(AuthToken.user_id)
    )


def add_attempt(
    db: Session, account_key_hash: str, ip_hash: str, action: str, now: datetime
) -> None:
    db.add(
        LoginAttempt(
            account_key_hash=account_key_hash, ip_hash=ip_hash, action=action, created_at=now
        )
    )


def nth_recent_attempt_time(
    db: Session,
    actions: tuple[str, ...],
    nth: int,
    account_key_hash: str | None,
    ip_hash: str | None,
) -> datetime | None:
    statement = select(LoginAttempt.created_at).where(LoginAttempt.action.in_(actions))
    if account_key_hash is not None:
        statement = statement.where(LoginAttempt.account_key_hash == account_key_hash)
    if ip_hash is not None:
        statement = statement.where(LoginAttempt.ip_hash == ip_hash)
    statement = statement.order_by(LoginAttempt.created_at.desc()).offset(nth - 1).limit(1)
    return db.scalar(statement)


def clear_attempts(db: Session, account_key_hash: str, action: str) -> None:
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.account_key_hash == account_key_hash, LoginAttempt.action == action
        )
    )


def purge_expired(
    db: Session, now: datetime, idle_cutoff: datetime, attempt_cutoff: datetime
) -> None:
    db.execute(
        delete(AuthSession).where(
            or_(
                AuthSession.expires_at <= now,
                and_(AuthSession.user_id.is_not(None), AuthSession.last_seen_at <= idle_cutoff),
            )
        )
    )
    db.execute(delete(AuthToken).where(AuthToken.expires_at <= now))
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at <= attempt_cutoff))

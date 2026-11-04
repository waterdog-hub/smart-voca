#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 메일 발송 인터페이스와 인증 메일 문구 (개발: 콘솔 출력)
# 파일 위치: src/web/services/mail_service.py

import sys
from dataclasses import dataclass
from typing import Protocol

from web.settings import Settings


@dataclass(frozen=True)
class MailMessage:
    recipient: str
    subject: str
    body: str


class MailSendError(Exception):
    """메일을 보내지 못했다. 발송 구현은 모든 실패를 이 예외로 바꿔 던진다."""


class Mailer(Protocol):
    def send(self, message: MailMessage) -> None: ...


class ConsoleMailer:
    """개발용. 메일 대신 콘솔에 출력해 업체 없이 링크를 눌러 볼 수 있게 한다."""

    def send(self, message: MailMessage) -> None:
        text = f"\n[개발용 메일] 받는 사람: {message.recipient}\n제목: {message.subject}\n{message.body}\n"
        # 한글 Windows 콘솔(cp949)에 없는 글자가 있어도 메일 처리가 실패하지 않게 한다
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, "replace").decode(encoding), flush=True)


class UnconfiguredMailer:
    """운영용 임시 구현. 콘솔 출력은 로그에 링크를 남기므로 발송 업체를 정할 때까지 실패시킨다."""

    def send(self, message: MailMessage) -> None:
        raise MailSendError("메일 발송 업체가 설정되지 않았습니다.")


def create_mailer(settings: Settings) -> Mailer:
    return UnconfiguredMailer() if settings.is_production else ConsoleMailer()


def build_verification_message(recipient: str, public_base_url: str, token: str) -> MailMessage:
    # 토큰을 URL 조각(#)에 넣는다. 조각은 서버로 전송되지 않아 접속 로그에 남지 않는다 (이슈 #9)
    link = f"{public_base_url}/verify-email#token={token}"
    return MailMessage(
        recipient=recipient,
        subject="[smart-voca] 이메일 인증을 완료해 주세요",
        body=(
            "아래 링크를 눌러 이메일 인증을 완료해 주세요. 링크는 24시간 동안 유효합니다.\n\n"
            f"{link}\n\n"
            "본인이 가입하지 않았다면 이 메일을 무시해 주세요."
        ),
    )


def build_already_registered_message(recipient: str, public_base_url: str) -> MailMessage:
    return MailMessage(
        recipient=recipient,
        subject="[smart-voca] 이미 가입된 이메일입니다",
        body=(
            "이 이메일로 가입 요청이 있었지만 이미 가입되어 있습니다. "
            "아래 주소에서 로그인해 주세요.\n\n"
            f"{public_base_url}/login\n\n"
            "본인이 요청하지 않았다면 이 메일을 무시해 주세요."
        ),
    )

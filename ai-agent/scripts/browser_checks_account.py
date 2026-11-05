#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 비밀번호 재설정, 내 계정, 탈퇴 화면 점검 (테스트 정의서 §4)
# 파일 위치: ai-agent/scripts/browser_checks_account.py

import re

from browser_check_lib import PHONE_WIDTH, Session, TEST_PASSWORD

NEW_PASSWORD = "another long passphrase 42"
RESET_NEW_PASSWORD = "reset long passphrase 77"
WRONG_PASSWORD = "wrong password here"


def _mail_link(session: Session, email: str, path: str) -> str:
    log_text = session.log_path.read_bytes().decode("utf-8", "replace")
    pattern = rf"받는 사람: {re.escape(email)}.*?(http\S+/{path}#token=[\w-]+)"
    return re.findall(pattern, log_text, flags=re.DOTALL)[-1]


def _message_has(browser, text: str) -> bool:
    return browser.wait(f"document.getElementById('message').textContent.includes({text!r})")


def _log_in_with(session: Session, email: str, password: str) -> bool:
    browser = session.browser
    browser.go(f"{session.base}/login")
    browser.fill(email=email, password=password)
    browser.submit("login-form")
    return browser.wait("location.pathname==='/' && !!document.getElementById('logout-button')")


def check_account_flow(session: Session) -> None:
    """재설정 요청·완료, 내 계정의 변경과 탈퇴 (테스트 정의서 §4.9)."""
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-account@example.com"
    browser.resize(PHONE_WIDTH, 800, mobile=True)

    browser.go(f"{base}/forgot-password")
    check("재설정 요청 화면에 시연 안내가 없음 (개발 환경)", browser.js("!document.getElementById('demo-reset-note')"))
    browser.fill(email="nobody@example.com")
    browser.submit("forgot-form")
    check("가입 여부와 상관없는 안내 문구", _message_has(browser, "가입된 이메일이면"), browser.text("message"))
    browser.shot("forgot_375.png")

    session.sign_up(email, "계정점검")
    check("로그인", session.log_in(email))
    browser.go(session.verification_link(email))
    browser.wait("document.getElementById('verify-status').textContent.includes('완료')")

    browser.go(f"{base}/account")
    browser.wait("!!document.getElementById('name-form')")
    current_link = "document.querySelector('.member-nav a[aria-current=page][href=\"/account\"]')"
    check("메뉴에 내 계정 표시", browser.js(f"!!{current_link}"))
    check("내 이메일 표시", browser.text("account-email") == email, browser.text("account-email"))
    check("375px 폭에 가로 스크롤 없음", browser.js("document.documentElement.scrollWidth<=window.innerWidth"))
    browser.shot("account_375.png")

    browser.fill(display_name="새이름")
    browser.submit("name-form")
    check("표시 이름 저장 안내", _message_has(browser, "저장했습니다"), browser.text("message"))
    check("메뉴의 이름이 바뀜", "새이름" in browser.js("document.querySelector('.member-nav-user span').textContent"))

    browser.fill(current_password=WRONG_PASSWORD, new_password=NEW_PASSWORD)
    browser.submit("password-form")
    check(
        "현재 비밀번호가 틀리면 칸 아래에 안내",
        browser.wait("!document.getElementById('current_password-error').hidden"),
    )
    browser.fill(current_password=TEST_PASSWORD, new_password="short")
    browser.submit("password-form")
    check("약한 새 비밀번호는 칸 아래에 안내", browser.wait("!document.getElementById('new_password-error').hidden"))
    browser.fill(current_password=TEST_PASSWORD, new_password=NEW_PASSWORD)
    browser.submit("password-form")
    check("비밀번호 변경 안내", _message_has(browser, "바꿨습니다"), browser.text("message"))
    check("변경 뒤 입력칸이 비워짐", browser.js("document.getElementById('current_password').value===''"))

    check("로그아웃", session.log_out())
    check("옛 비밀번호로는 로그인되지 않음", not _log_in_with(session, email, TEST_PASSWORD))
    check("새 비밀번호로 로그인", _log_in_with(session, email, NEW_PASSWORD))
    check("로그아웃 2", session.log_out())

    browser.go(f"{base}/login")
    check("로그인 화면에 재설정 링크", browser.js("!!document.querySelector('a[href=\"/forgot-password\"]')"))
    browser.go(f"{base}/forgot-password")
    browser.fill(email=email)
    browser.submit("forgot-form")
    _message_has(browser, "가입된 이메일이면")
    link = _mail_link(session, email, "reset-password")
    token = link.split("#token=", 1)[1]
    browser.go(link)
    browser.wait("!!document.getElementById('reset-form')")
    check("주소창에서 재설정 토큰 제거", token not in browser.js("location.href"))
    log_text = session.log_path.read_bytes().decode("utf-8", "replace")
    log_without_links = re.sub(r"http\S+/(?:verify-email|reset-password)#token=[\w-]+", "", log_text)
    check("서버 접속 로그에 재설정 토큰 없음", token not in log_without_links)
    browser.fill(new_password=RESET_NEW_PASSWORD, new_password_again="different passphrase 11")
    browser.submit("reset-form")
    check("두 비밀번호가 다르면 안내", browser.wait("!document.getElementById('new_password_again-error').hidden"))
    browser.fill(new_password="short", new_password_again="short")
    browser.submit("reset-form")
    check("약한 비밀번호는 서버가 거절", browser.wait("!document.getElementById('new_password-error').hidden"))
    browser.shot("reset_375.png")
    browser.fill(new_password=RESET_NEW_PASSWORD, new_password_again=RESET_NEW_PASSWORD)
    browser.submit("reset-form")
    check("재설정 완료 후 로그인 화면으로 이동", browser.wait("location.pathname==='/login'", timeout=15))
    check("옛 비밀번호는 거절", not _log_in_with(session, email, NEW_PASSWORD))
    check("재설정한 비밀번호로 로그인", _log_in_with(session, email, RESET_NEW_PASSWORD))
    check("로그아웃 3", session.log_out())
    browser.go(link)
    browser.wait("!!document.getElementById('reset-form')")
    browser.fill(new_password=NEW_PASSWORD, new_password_again=NEW_PASSWORD)
    browser.submit("reset-form")
    check("사용한 링크는 실패 안내", _message_has(browser, "만료"), browser.text("message"))

    check("재설정 뒤 다시 로그인", _log_in_with(session, email, RESET_NEW_PASSWORD))
    browser.go(f"{base}/account")
    browser.wait("!!document.getElementById('logout-all-button')")
    browser.click("logout-all-button")
    check("모든 기기 로그아웃 후 로그인 화면", browser.wait("location.pathname==='/login'"))

    check("탈퇴 전 로그인", _log_in_with(session, email, RESET_NEW_PASSWORD))
    browser.go(f"{base}/account")
    browser.wait("!!document.getElementById('delete-form')")
    browser.js("window.confirm=()=>true")
    browser.fill(delete_password=RESET_NEW_PASSWORD, delete_confirm="")
    browser.submit("delete-form")
    check("확인 단어가 없으면 안내", browser.wait("!document.getElementById('confirm-error').hidden"))
    browser.fill(delete_password=WRONG_PASSWORD, delete_confirm="탈퇴")
    browser.submit("delete-form")
    check("비밀번호가 틀리면 탈퇴되지 않고 안내", browser.wait("!document.getElementById('password-error').hidden"))
    check("틀린 뒤에도 계정 화면에 머무름", browser.js("location.pathname") == "/account")
    browser.fill(delete_password=RESET_NEW_PASSWORD, delete_confirm="탈퇴")
    browser.submit("delete-form")
    check(
        "탈퇴 후 안내와 함께 로그인 화면",
        browser.wait("location.pathname==='/login' && !!document.getElementById('withdrawn-notice')"),
    )
    check("탈퇴한 계정은 로그인되지 않음", not _log_in_with(session, email, RESET_NEW_PASSWORD))

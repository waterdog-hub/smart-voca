#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 설정 화면 점검 (테스트 정의서 §4)
# 파일 위치: ai-agent/scripts/browser_checks_settings.py

import json

from browser_check_lib import Browser, DESKTOP_WIDTH, PHONE_WIDTH, Session


def _settings_loaded(browser: Browser) -> bool:
    return browser.wait("!document.getElementById('settings-save').disabled")


def _type_number(browser: Browser, element_id: str, value: str) -> None:
    # 값만 넣으면 input 이벤트가 나지 않으므로 사람이 입력할 때처럼 이벤트를 함께 보낸다
    browser.js(
        f"(()=>{{const e=document.getElementById({json.dumps(element_id)});"
        f"e.value={json.dumps(value)};e.dispatchEvent(new Event('input',{{bubbles:true}}));}})()"
    )


def _error_visible(browser: Browser, name: str) -> bool:
    return browser.js(f"!document.getElementById('{name}-error').hidden")


def check_settings_flow(session: Session) -> None:
    """설정 (테스트 정의서 §4.5)."""
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-settings@example.com"
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)

    browser.go(f"{base}/settings")
    check("로그인 없이 설정을 열면 로그인 화면으로 이동", browser.js("location.pathname") == "/login")

    session.sign_up(email, "설정")
    session.log_in(email)
    browser.go(f"{base}/settings")
    check("설정 값을 불러온 뒤 저장 버튼이 켜짐", _settings_loaded(browser))
    check("기본값 표시", browser.js("document.getElementById('daily_new_count').value") == "20")
    check(
        "인증 전 저장 버튼은 비활성으로 표시",
        browser.js("document.getElementById('settings-save').getAttribute('aria-disabled')==='true'"),
    )
    browser.fill(daily_new_count="33")
    browser.submit("settings-form")
    check("인증 전 저장은 안내만 표시", browser.wait("document.getElementById('message').textContent.includes('이메일 인증')"))
    browser.go(f"{base}/settings")
    _settings_loaded(browser)
    check("인증 전 값이 저장되지 않음", browser.js("document.getElementById('daily_new_count').value") == "20")

    browser.go(session.verification_link(email))
    browser.wait("document.getElementById('verify-status').textContent.includes('완료')")
    browser.go(f"{base}/settings")
    _settings_loaded(browser)
    check("메뉴에 현재 화면 표시", browser.js("document.querySelector('a[href=\"/settings\"]').getAttribute('aria-current')==='page'"))

    _type_number(browser, "daily_new_count", "0")
    check("잘못된 값은 저장 전에 칸 아래에 안내", _error_visible(browser, "daily_new_count"))
    check("칸 안내에 범위가 나옴", "1 이상" in browser.text("daily_new_count-error"))
    check(
        "잘못된 칸에 오류 표시 속성",
        browser.js("document.getElementById('daily_new_count').getAttribute('aria-invalid')==='true'"),
    )
    browser.submit("settings-form")
    check("잘못된 값은 저장하지 않고 안내", browser.wait("document.getElementById('message').textContent.includes('입력값')"))
    _type_number(browser, "daily_new_count", "12")
    check("값을 고치면 칸 안내가 사라짐", not _error_visible(browser, "daily_new_count"))

    _type_number(browser, "daily_review_count", "0")
    check("복습 0은 허용", not _error_visible(browser, "daily_review_count"))
    browser.fill(test_format="subjective", test_direction="both")
    browser.submit("settings-form")
    check("저장 완료 안내", browser.wait("document.getElementById('message').textContent.includes('저장했습니다')"))
    check("저장 후 버튼이 다시 켜짐", browser.wait("!document.getElementById('settings-save').disabled"))

    _type_number(browser, "daily_new_count", "99")
    browser.click("settings-revert")
    check("되돌리기는 마지막 저장 값으로 복원", browser.js("document.getElementById('daily_new_count').value") == "12")

    _type_number(browser, "wrong_threshold", "0")
    browser.click("settings-revert")
    check("되돌리기는 칸 안내도 지움", not _error_visible(browser, "wrong_threshold"))

    browser.go(f"{base}/settings")
    _settings_loaded(browser)
    saved = browser.js(
        "['daily_new_count','daily_review_count','test_format','test_direction']"
        ".map(id=>document.getElementById(id).value).join(',')"
    )
    check("새로고침 후에도 저장 값 유지", saved == "12,0,subjective,both", saved)

    browser.resize(PHONE_WIDTH, 800, mobile=True)
    browser.go(f"{base}/settings")
    _settings_loaded(browser)
    check(
        "375px 폭에서 가로 스크롤 없음",
        browser.js("document.documentElement.scrollWidth<=document.documentElement.clientWidth"),
    )
    browser.shot("settings-phone.png")
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)
    browser.go(f"{base}/settings")
    _settings_loaded(browser)
    browser.shot("settings-desktop.png")
    session.log_out()

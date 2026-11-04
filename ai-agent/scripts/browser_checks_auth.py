#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 가입, 로그인, 이메일 인증 화면 점검 (테스트 정의서 §4)
# 파일 위치: ai-agent/scripts/browser_checks_auth.py

from browser_check_lib import PHONE_WIDTH, Session, TEST_PASSWORD


def check_auth_flow(session: Session) -> None:
    """가입, 로그인, 이메일 인증, 로그아웃 (테스트 정의서 §4.1)."""
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-auth@example.com"
    browser.resize(PHONE_WIDTH, 720, mobile=True)

    browser.go(f"{base}/")
    check("로그인 없이 홈을 열면 시작 화면 표시", browser.js("document.querySelector('main').dataset.page") == "landing")
    check("시작 화면에 가입과 로그인 링크", browser.js("!!document.getElementById('landing-signup') && !!document.getElementById('landing-login')"))
    check("개발 환경에는 시연 안내가 없음", browser.js("!document.getElementById('demo-notice')"))

    browser.go(f"{base}/signup")
    browser.fill(
        email=email,
        password="password",
        display_name="브라우저",
        terms_agreed=True,
        privacy_agreed=True,
    )
    browser.submit("signup-form")
    check(
        "흔한 비밀번호는 칸 아래에 오류 표시",
        browser.wait(
            "!document.getElementById('password-error').hidden"
            " && document.getElementById('password').getAttribute('aria-invalid')==='true'"
        ),
    )
    check("오류 후 제출 버튼 복구", browser.wait("!document.querySelector('button[type=submit]').disabled"))
    browser.shot("signup_error_375.png")
    check("375px 폭에서 가로 스크롤 없음", browser.js("document.documentElement.scrollWidth<=window.innerWidth"))
    browser.fill(password=TEST_PASSWORD)
    browser.submit("signup-form")
    check("가입 후 인증 메일 안내로 이동", browser.wait("location.pathname==='/signup/sent'"))

    browser.go(f"{base}/login")
    browser.fill(email=email, password="wrong password here")
    browser.submit("login-form")
    check("틀린 비밀번호 안내", browser.wait("document.getElementById('message').textContent.includes('올바르지')"))
    browser.fill(password=TEST_PASSWORD)
    browser.submit("login-form")
    check("로그인 후 홈으로 이동", browser.wait("location.pathname==='/' && !!document.getElementById('logout-button')"))
    browser.ready()
    check("인증 안내 띠 표시", browser.js("!!document.getElementById('verify-banner')"))
    check("세션 쿠키를 자바스크립트에서 읽을 수 없음", "sv_session" not in (browser.js("document.cookie") or ""))
    gap = browser.js(
        "document.querySelector('.member-main').getBoundingClientRect().top"
        "-document.querySelector('.member-nav').getBoundingClientRect().bottom"
    )
    check("짧은 휴대폰 화면에서 메뉴 아래가 벌어지지 않음", abs(gap) <= 1, gap)
    browser.shot("home_unverified_375.png")

    browser.click("resend-button")
    check(
        "1분 안의 재발송은 남은 시간 안내",
        browser.wait("document.getElementById('message').textContent.includes('후 가능')"),
        browser.text("message"),
    )

    link = session.verification_link(email)
    token = link.split("#token=", 1)[1]
    browser.go(link)
    verified = "document.getElementById('verify-status').textContent.includes('완료')"
    check("메일 링크로 인증 완료", browser.wait(verified), browser.text("verify-status"))
    check("주소창에서 토큰 제거", token not in browser.js("location.href"))
    check("서버 접속 로그에 토큰 없음", token not in session.log_without_mail_links())
    browser.shot("verify_ok_375.png")
    expired = "document.getElementById('verify-status').textContent.includes('만료')"
    browser.go(link)
    check("같은 탭에 사용한 링크를 붙여 넣으면 실패 안내", browser.wait(expired), browser.text("verify-status"))
    browser.go("about:blank")
    browser.go(link)
    check("사용한 링크를 새로 열어도 실패 안내", browser.wait(expired), browser.text("verify-status"))

    browser.go(f"{base}/")
    check("인증 후 안내 띠 사라짐", browser.js("!document.getElementById('verify-banner')"))
    check("로그아웃 후 로그인 화면으로 이동", session.log_out())
    browser.go(f"{base}/words")
    check("로그아웃 후 회원 화면 차단", browser.js("location.pathname") == "/login")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 홈, 암기, 일차 보기, 로그인 후 복귀 점검 (테스트 정의서 §4.6)
# 파일 위치: ai-agent/scripts/browser_checks_learning.py

from browser_check_lib import DESKTOP_WIDTH, PHONE_WIDTH, Browser, Session
from browser_checks_words import _add_word

SPACE = (" ", "Space", 32, " ")
ARROW_UP = ("ArrowUp", "ArrowUp", 38)
ARROW_RIGHT = ("ArrowRight", "ArrowRight", 39)
ARROW_LEFT = ("ArrowLeft", "ArrowLeft", 37)
KEY_1 = ("1", "Digit1", 49, "1")
KEY_2 = ("2", "Digit2", 50, "2")


def _hidden(browser: Browser, element_id: str) -> bool:
    # 속성이 아니라 실제 표시 여부를 본다. CSS가 hidden을 덮어쓰면 속성만으로는 알 수 없다
    return browser.js(f"getComputedStyle(document.getElementById('{element_id}')).display==='none'")


def _card_ready(browser: Browser) -> bool:
    return browser.wait("!document.getElementById('memorize-card').hidden")


def _word(browser: Browser) -> str:
    return browser.text("card-word")


def _word_changes_from(browser: Browser, word: str) -> bool:
    return browser.wait(
        f"document.getElementById('card-word').textContent!=={word!r} "
        "|| !document.getElementById('memorize-summary').hidden"
    )


def _set_day_size(browser: Browser, base: str, new_count: int) -> None:
    browser.go(f"{base}/settings")
    browser.wait("!document.getElementById('settings-save').disabled")
    browser.fill(daily_new_count=str(new_count), daily_review_count="1")
    browser.submit("settings-form")
    browser.wait("document.getElementById('message').textContent.includes('저장했습니다')")


def _no_horizontal_scroll(browser: Browser) -> bool:
    return browser.js("document.documentElement.scrollWidth<=document.documentElement.clientWidth")


def check_home_and_memorize(session: Session) -> None:
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-learning@example.com"
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)

    session.sign_up(email, "암기")
    session.log_in(email)
    browser.go(session.verification_link(email))
    browser.wait("document.getElementById('verify-status').textContent.includes('완료')")

    browser.go(f"{base}/")
    check("빈 단어장이면 홈이 단어장으로 안내", browser.js("document.getElementById('home-state').dataset.state") == "no-words")
    browser.go(f"{base}/memorize")
    check("진도가 없으면 암기 화면이 홈으로 안내", not _hidden(browser, "memorize-empty"))

    browser.go(f"{base}/words")
    browser.wait("document.getElementById('word-table-area').getAttribute('aria-busy')==='false'")
    for word, meaning in (("alpha", "첫째"), ("bravo", "둘째"), ("charlie", "셋째")):
        _add_word(browser, word, meaning)
        browser.wait(f"document.getElementById('message').textContent.includes('{word}')")
    _set_day_size(browser, base, 2)

    browser.go(f"{base}/")
    check("단어가 있으면 다음 일차 만들기 표시", browser.js("!!document.querySelector('[data-create-plan]')"))
    browser.js("document.querySelector('[data-create-plan]').click()")
    check("일차를 만들면 암기 화면으로 이동", browser.wait("location.pathname==='/memorize'"))
    check("첫 카드 표시", _card_ready(browser) and _word(browser) == "alpha")
    check("뜻은 처음에 가려짐", _hidden(browser, "card-meaning"))
    check("뜻을 보기 전에는 외움과 다시 버튼이 보이지 않음", _hidden(browser, "card-actions"))
    browser.shot("memorize_1280.png")

    browser.press(*ARROW_RIGHT)
    browser.press(*KEY_1)
    browser.press(*ARROW_LEFT)
    check("뜻을 보기 전에는 외움과 다시 키가 동작하지 않음", _word(browser) == "alpha")

    browser.press(*ARROW_UP)
    check("↑ 키로 뜻 표시", not _hidden(browser, "card-meaning") and browser.text("card-meaning") == "첫째")
    check("뜻을 본 뒤 버튼 표시", not _hidden(browser, "card-actions"))
    browser.press(*ARROW_LEFT)
    check("← 키는 다음 카드로 넘어감", _word_changes_from(browser, "alpha") and _word(browser) == "bravo")
    check("다시는 완료 수를 늘리지 않음", "0개 완료" in browser.text("memorize-progress-text"))

    browser.go(f"{base}/memorize")
    _card_ready(browser)
    check("다시 들어오면 뒤로 보낸 카드 다음부터 이어 감", _word(browser) == "bravo")

    browser.press(*SPACE)
    check("Space 키로 뜻 표시", not _hidden(browser, "card-meaning"))
    browser.press(*SPACE)
    check("뜻이 보일 때 Space를 다시 눌러도 넘어가지 않음", _word(browser) == "bravo")
    browser.press(*KEY_1)
    check("1 키로 외움", _word_changes_from(browser, "bravo") and _word(browser) == "alpha")
    check("외움은 완료 수를 늘림", "1개 완료" in browser.text("memorize-progress-text"))

    browser.js("document.getElementById('show-meaning').focus()")
    browser.press(*SPACE)
    check("버튼에 포커스가 있어도 Space가 한 번만 처리됨", not _hidden(browser, "card-meaning") and _word(browser) == "alpha")
    browser.press(*KEY_2)
    check("2 키로 다시", browser.wait("document.getElementById('card-meaning').hidden") and _word(browser) == "alpha")
    browser.click("show-meaning")
    browser.click("remember-button")
    check("마지막 카드 뒤 요약 표시", browser.wait("!document.getElementById('memorize-summary').hidden"))
    check("요약에 외운 수 표시", "외운 단어 2개" in browser.text("summary-text"))
    check("요약에 다음 일차 버튼 표시", browser.js("!document.querySelector('[data-create-plan]').hidden"))

    browser.go(f"{base}/")
    check("끝낸 뒤 홈에 전체 진행률 표시", "3개 중 2개" in browser.text("overall-progress"))
    browser.js("document.querySelector('[data-create-plan]').click()")
    browser.wait("location.pathname==='/memorize'")
    _card_ready(browser)
    check("2일차는 새 단어부터 표시", _word(browser) == "charlie")
    check("드롭다운 기본값은 현재 일차", browser.js("document.getElementById('day-select').value") == "2")

    browser.go(f"{base}/")
    check("미완료면 홈에 이어서 암기하기 표시", browser.js("!!document.getElementById('continue-link')"))

    browser.go(f"{base}/memorize")
    _card_ready(browser)
    browser.js(
        "(()=>{const s=document.getElementById('day-select');s.value='1';"
        "s.dispatchEvent(new Event('change',{bubbles:true}));})()"
    )
    check("드롭다운으로 지난 일차 이동", browser.wait("location.search==='?day=1'"))
    _card_ready(browser)
    check("지난 일차에 복습 안내 표시", not _hidden(browser, "review-notice"))
    check("지난 일차는 모든 카드를 다시 보여 줌", browser.js("document.getElementById('memorize-progress').max") == 2)
    first_card = _word(browser)
    browser.press(*ARROW_UP)
    browser.press(*ARROW_RIGHT)
    check("지난 일차에서도 외움으로 넘어감", _word_changes_from(browser, first_card))
    browser.press(*ARROW_UP)
    browser.press(*ARROW_RIGHT)
    check("지난 일차 복습 요약 표시", browser.wait("!document.getElementById('memorize-summary').hidden"))
    browser.go(f"{base}/")
    check("지난 일차 복습은 전체 진행률을 바꾸지 않음", "3개 중 2개" in browser.text("overall-progress"))
    check("지난 일차 복습은 현재 일차를 바꾸지 않음", "2일차" in browser.text("home-state"))

    browser.go(f"{base}/plans?day=1")
    check("일차 보기에 단어와 완료 여부 표시", browser.js("document.querySelectorAll('#plan-table tbody tr').length") == 2)
    check("일차 보기는 수정 버튼이 없음", browser.js("document.querySelectorAll('#plan-table button').length") == 0)

    browser.resize(PHONE_WIDTH, 720, mobile=True)
    browser.go(f"{base}/memorize")
    _card_ready(browser)
    browser.click("show-meaning")
    check("375px 폭 암기 화면에 가로 스크롤 없음", _no_horizontal_scroll(browser))
    browser.shot("memorize_375.png")
    browser.go(f"{base}/plans?day=1")
    check("375px 폭 일차 보기에 가로 스크롤 없음", _no_horizontal_scroll(browser))
    browser.go(f"{base}/")
    check("375px 폭 홈에 가로 스크롤 없음", _no_horizontal_scroll(browser))
    browser.shot("home_375.png")
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)
    browser.go(f"{base}/")
    browser.shot("home_1280.png")

    # 로그인 후 원래 페이지로 복귀 (재검토 7번)
    session.log_out()
    browser.go(f"{base}/plans?day=1")
    check("로그인 화면 주소에 원래 페이지 유지", browser.js("location.search").startswith("?next="))
    browser.fill(email=email, password=session.password)
    browser.submit("login-form")
    check("로그인 후 원래 페이지로 복귀", browser.wait("location.pathname==='/plans' && location.search==='?day=1'"))
    session.log_out()
    for unsafe in ("//evil.example/", "https://evil.example/", "/\\evil.example", "javascript:alert(1)"):
        browser.go(f"{base}/login?next={unsafe}")
        browser.fill(email=email, password=session.password)
        browser.submit("login-form")
        reached = browser.wait("location.pathname==='/' && !!document.getElementById('logout-button')")
        same_site = browser.js("location.origin") == base
        check(f"외부 주소로 이동하지 않음: {unsafe}", reached and same_site)
        session.log_out()

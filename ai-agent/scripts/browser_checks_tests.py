#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시험 시작, 진행, 결과, 기록, 홈의 최근 시험 점검 (테스트 정의서 §4.7)
# 파일 위치: ai-agent/scripts/browser_checks_tests.py

import json

from browser_check_lib import DESKTOP_WIDTH, PHONE_WIDTH, Browser, Session
from browser_checks_words import GREEK_MORE_TITLE, GREEK_TITLE, add_wordbook

KEY_2 = ("2", "Digit2", 50, "2")
KEY_3 = ("3", "Digit3", 51, "3")
ENTER = ("Enter", "Enter", 13, "\r")


def _shown(browser: Browser, element_id: str) -> bool:
    # 속성이 아니라 실제 표시 여부를 본다
    return browser.js(f"getComputedStyle(document.getElementById('{element_id}')).display!=='none'")


def _start_test(browser: Browser, test_format: str, test_direction: str, count: int) -> bool:
    browser.wait("!!document.getElementById('test-start-form')")
    browser.fill(test_format=test_format, test_direction=test_direction, count=str(count))
    browser.js("document.getElementById('test_format').dispatchEvent(new Event('change',{bubbles:true}))")
    browser.submit("test-start-form")
    return browser.wait("/^\\/tests\\/\\d+$/.test(location.pathname)") and browser.wait(
        "getComputedStyle(document.getElementById('question-area')).display!=='none'"
    )


def _no_horizontal_scroll(browser: Browser) -> bool:
    return browser.js("document.documentElement.scrollWidth<=document.documentElement.clientWidth")


def _choice_checked(browser: Browser, index: int) -> bool:
    return browser.js(f"document.querySelectorAll('#choice-list input')[{index}].checked")


def check_tests_flow(session: Session) -> None:
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-tests@example.com"
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)

    session.sign_up(email, "시험")
    session.log_in(email)
    browser.go(session.verification_link(email))
    browser.wait("document.getElementById('verify-status').textContent.includes('완료')")

    browser.go(f"{base}/tests")
    browser.wait("!!document.getElementById('test-start')")
    check("단어가 없으면 시험 시작 버튼 비활성", browser.js("document.getElementById('test-start').disabled"))
    check("단어가 없으면 이유 표시", "단어" in browser.text("test-not-possible"))
    browser.go(f"{base}/tests/history")
    check("기록이 없으면 빈 상태 안내", _shown(browser, "history-empty"))

    check("점검용 단어장 담기 (단어 3개)", add_wordbook(browser, base, GREEK_TITLE))

    browser.go(f"{base}/tests")
    browser.wait("!!document.getElementById('test-start')")
    check("객관식은 단어 3개로 시작할 수 없음", browser.js("document.getElementById('test-start').disabled"))
    check("부족한 단어 수를 안내", "4개" in browser.text("test-not-possible"))
    browser.js(
        "(()=>{const s=document.getElementById('test_format');s.value='subjective';"
        "s.dispatchEvent(new Event('change',{bubbles:true}));})()"
    )
    check("주관식을 고르면 시작 가능", not browser.js("document.getElementById('test-start').disabled"))

    check("점검용 단어장 추가로 담기 (단어 2개 더)", add_wordbook(browser, base, GREEK_MORE_TITLE))

    # 객관식과 키보드
    browser.go(f"{base}/tests")
    browser.fill(count="0")
    browser.submit("test-start-form")
    check("문항 수가 틀리면 칸 아래에 안내", browser.wait("!document.getElementById('count-error').hidden"))
    check("객관식 시작 후 진행 화면으로 이동", _start_test(browser, "multiple", "en_ko", 3))
    check("보기 4개 표시", browser.js("document.querySelectorAll('#choice-list input').length") == 4)
    check("주관식 입력칸은 숨김", not _shown(browser, "text-answer"))
    browser.shot("test_take_1280.png")
    first_question = browser.text("question-text")

    browser.press(*KEY_2)
    check("2 키로 보기 선택", _choice_checked(browser, 1))
    check("보기를 골라도 다음으로 넘어가지 않음", browser.text("question-text") == first_question)
    browser.press(*KEY_3)
    check("다른 숫자로 답을 고칠 수 있음", _choice_checked(browser, 2) and not _choice_checked(browser, 1))
    browser.press(*ENTER)
    check("숫자키로 고른 뒤 Enter로 다음 문항", browser.wait(f"document.getElementById('question-text').textContent!=={json.dumps(first_question)}"))
    check("이전 버튼 사용 가능", not browser.js("document.getElementById('prev-question').disabled"))

    browser.js("location.reload()")
    browser.wait("document.readyState==='complete' && getComputedStyle(document.getElementById('question-area')).display!=='none'")
    check("새로고침 후 같은 문항에서 이어 감", browser.wait(f"document.getElementById('question-text').textContent!=={json.dumps(first_question)}"))
    browser.click("prev-question")
    check("새로고침 후 고른 답이 유지됨", browser.wait("document.querySelectorAll('#choice-list input')[2].checked"))

    browser.go(f"{base}/tests")
    check("시작 화면에 이어서 보기 표시", browser.wait("!!document.getElementById('continue-test')"))
    browser.js("window.__asked='';window.confirm=(text)=>{window.__asked=text;return false;}")
    browser.submit("test-start-form")
    check("새로 시작하면 확인 창", browser.wait("window.__asked.includes('그만두고')"))
    check("확인을 취소하면 이동하지 않음", browser.js("location.pathname") == "/tests")
    browser.click("continue-test")
    browser.wait("/^\\/tests\\/\\d+$/.test(location.pathname)")
    browser.wait("document.readyState==='complete' && getComputedStyle(document.getElementById('question-area')).display!=='none'")

    # 마지막 문항까지 가서 제출 확인
    browser.wait("document.getElementById('question-text').textContent!==''")
    for _ in range(3):
        if browser.text("next-question") == "제출":
            break
        browser.click("next-question")
    check("마지막 문항에서 버튼이 제출로 바뀜", browser.text("next-question") == "제출")
    browser.js("window.__asked='';window.confirm=(text)=>{window.__asked=text;return false;}")
    browser.click("next-question")
    check("미응답 수를 알리고 확인", browser.wait("window.__asked.includes('2개')"))
    check("취소하면 제출하지 않음", _shown(browser, "question-area"))
    browser.js("window.confirm=()=>true")
    browser.click("next-question")
    check("제출 후 결과 표시", browser.wait("getComputedStyle(document.getElementById('test-result')).display!=='none'"))
    check("진행 화면은 숨김", not _shown(browser, "question-area"))
    check("결과에 문항별 행 표시", browser.js("document.querySelectorAll('#result-rows tr').length") == 3)
    check("미응답은 답 없음으로 표시", "(답 없음)" in browser.text("result-rows"))
    if _shown(browser, "wrong-only"):
        browser.click("wrong-only")
        wrong_rows = browser.js("document.querySelectorAll('#result-rows tr').length")
        marked = browser.js("[...document.querySelectorAll('#result-rows tr')].every(r=>r.lastChild.textContent==='오답')")
        check("틀린 문항만 보기", wrong_rows >= 2 and marked)
        browser.click("wrong-only")
        check("전체 문항으로 되돌림", browser.js("document.querySelectorAll('#result-rows tr').length") == 3)
    browser.shot("test_result_1280.png")

    attempt_path = browser.js("location.pathname")
    browser.go(f"{base}{attempt_path}")
    check("제출한 시험을 다시 열면 점수만 표시", browser.wait("!!document.getElementById('finished-score')"))

    # 주관식, 입력칸의 숫자, Enter, HTML 이스케이프
    browser.go(f"{base}/tests")
    check("주관식 시작", _start_test(browser, "subjective", "en_ko", 5))
    check("주관식은 입력칸 표시", _shown(browser, "text-answer") and not _shown(browser, "choice-list"))
    check("입력칸에 포커스", browser.js("document.activeElement.id") == "text-answer-input")
    browser.press(*KEY_2)
    check("입력칸에서 숫자는 글자로 입력", browser.js("document.getElementById('text-answer-input').value") == "2")
    before = browser.text("question-progress-text")
    browser.press(*ENTER)
    check("입력칸에서 Enter로 다음 문항", browser.wait(f"document.getElementById('question-progress-text').textContent!=={json.dumps(before)}"))
    check("다음 문항은 입력칸이 비어 있음", browser.js("document.getElementById('text-answer-input').value") == "")

    questions = []
    for _ in range(5):
        questions.append(browser.text("question-text"))
        if browser.text("next-question") == "제출":
            break
        browser.click("next-question")
    check("단어에 넣은 HTML이 글자로 보임", any("<b>echo</b>" in text for text in questions), questions)
    check("문제 칸에 HTML이 실행되지 않음", browser.js("document.querySelectorAll('#question-text b, #question-text i').length") == 0)
    browser.js("window.confirm=()=>true")
    browser.click("next-question")
    browser.wait("getComputedStyle(document.getElementById('test-result')).display!=='none'")
    check("결과 표에 HTML이 실행되지 않음", browser.js("document.querySelectorAll('#result-rows b, #result-rows i').length") == 0)
    check("결과 표에 정답 글자 표시", "<i>다섯째" in browser.text("result-rows"))

    # 시험 기록과 홈
    browser.go(f"{base}/tests/history")
    check("시험 기록 2건 표시", browser.js("document.querySelectorAll('#history-table tbody tr').length") == 2)
    check("전체 정답률 표시", "시험 2회" in browser.text("history-summary"))
    browser.go(f"{base}/")
    check("홈에 최근 시험 표시", "주관식" in browser.text("latest-test"))

    # 세션이 끝나도 시험으로 돌아옴
    browser.go(f"{base}/tests")
    check("세션 복귀 점검용 시험 시작", _start_test(browser, "multiple", "ko_en", 2))
    attempt_path = browser.js("location.pathname")
    session.log_out()
    browser.go(f"{base}{attempt_path}")
    browser.wait("location.pathname==='/login'")
    browser.fill(email=email, password=session.password)
    browser.submit("login-form")
    check("로그인 후 시험으로 복귀", browser.wait(f"location.pathname==={json.dumps(attempt_path)}"))
    check("복귀 후 문제 복원", browser.wait("document.getElementById('question-text').textContent!==''"))

    browser.resize(PHONE_WIDTH, 720, mobile=True)
    browser.go(f"{base}{attempt_path}")
    browser.wait("getComputedStyle(document.getElementById('question-area')).display!=='none'")
    check("375px 폭 시험 진행에 가로 스크롤 없음", _no_horizontal_scroll(browser))
    browser.shot("test_take_375.png")
    browser.go(f"{base}/tests")
    check("375px 폭 시험 시작에 가로 스크롤 없음", _no_horizontal_scroll(browser))
    browser.go(f"{base}/tests/history")
    check("375px 폭 시험 기록에 가로 스크롤 없음", _no_horizontal_scroll(browser))
    browser.shot("test_history_375.png")
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)
    session.log_out()

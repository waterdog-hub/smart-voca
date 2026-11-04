#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 열려 있는 시연 주소를 실제 브라우저로 가입부터 시험까지 점검한다 (NFR-DEMO-01~03)
# 파일 위치: ai-agent/scripts/demo_check.py
#
# 실행 (프로젝트 루트, demo_server.py start를 띄운 뒤): .venv\Scripts\python ai-agent/scripts/demo_check.py 시연주소
# 시연 DB에 점검용 회원이 남으므로 끝난 뒤 demo_server.py reset을 실행한다.

import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from browser_check_lib import PHONE_WIDTH, Browser, Report, Session, find_browser, free_port, wait_for_url  # noqa: E402
from browser_checks_words import _add_word  # noqa: E402

WORDS = (("alpha", "첫째"), ("bravo", "둘째"), ("charlie", "셋째"), ("delta", "넷째"))
ARROW_UP = ("ArrowUp", "ArrowUp", 38)
ARROW_RIGHT = ("ArrowRight", "ArrowRight", 39)
WARNING_BUTTON = "[...document.querySelectorAll('button')].find(b=>/visit/i.test(b.textContent))"


def pass_ngrok_warning(browser: Browser, url: str) -> bool:
    """참가자처럼 경고 페이지의 Visit을 누른다. 경고가 나왔으면 True다."""
    browser.go(url)
    if not browser.wait(f"!!{WARNING_BUTTON}", timeout=5):
        return False
    browser.js(f"{WARNING_BUTTON}.click()")
    browser.wait("!!document.querySelector('.site-header')")
    browser.ready()
    return True


def run(base: str, work_dir: Path, report: Report) -> None:
    debug_port = free_port()
    process = subprocess.Popen(
        [
            find_browser(), "--headless=new", "--disable-gpu", "--no-first-run",
            f"--remote-debugging-port={debug_port}", f"--user-data-dir={work_dir / 'profile'}", "about:blank",
        ]
    )
    try:
        wait_for_url(f"http://127.0.0.1:{debug_port}/json/version")
        request = urllib.request.Request(f"http://127.0.0.1:{debug_port}/json/new", method="PUT")
        with urllib.request.urlopen(request) as response:
            debug_url = json.load(response)["webSocketDebuggerUrl"]
        browser = Browser(debug_url, work_dir)
        session = Session(base, browser, report, work_dir / "unused.log")
        check_flow(session, base)
    finally:
        process.terminate()
        process.wait(10)


def check_flow(session: Session, base: str) -> None:
    browser, check = session.browser, session.report.check
    email = f"rehearsal-{secrets.token_hex(4)}@example.com"
    browser.resize(PHONE_WIDTH, 800, mobile=True)

    warned = pass_ngrok_warning(browser, f"{base}/")
    print(f"INFO ngrok 경고 페이지 {'나옴' if warned else '안 나옴'}", flush=True)
    check("시작 화면 표시", browser.wait("document.querySelector('main').dataset.page==='landing'"))
    check("시연 안내 표시", browser.js("!!document.getElementById('demo-notice')"))
    browser.shot("demo_landing_375.png")

    browser.go(f"{base}/docs")
    check("API 문서가 닫혀 있음", "swagger" not in (browser.js("document.documentElement.outerHTML") or "").lower())

    session.sign_up(email, "리허설")
    check("가입 뒤 안내에 메일 대신 로그인 안내", "로그인" in browser.js("document.querySelector('main').textContent"))
    check("가입 뒤 로그인", session.log_in(email))
    cookies = browser.call("Network.getCookies", urls=[base])["cookies"]
    session_cookie = next((cookie for cookie in cookies if cookie["name"] == "sv_session"), None)
    check("세션 쿠키가 Secure와 HttpOnly", bool(session_cookie and session_cookie["secure"] and session_cookie["httpOnly"]))
    check("인증 안내 띠 없음 (자동 인증)", browser.js("!document.getElementById('verify-banner')"))

    browser.go(f"{base}/words")
    browser.wait("document.getElementById('word-table-area').getAttribute('aria-busy')==='false'")
    for index, (word, meaning) in enumerate(WORDS):
        _add_word(browser, word, meaning)
        browser.wait(f"document.getElementById('word-total').textContent.includes('{index + 1}')")
    check("단어 추가", "4" in browser.text("word-total"))

    browser.go(f"{base}/")
    browser.js("document.querySelector('[data-create-plan]').click()")
    check("일차 생성 후 암기 화면", browser.wait("location.pathname==='/memorize'"))
    browser.wait("!document.getElementById('memorize-card').hidden")
    for _ in WORDS:
        current = browser.text("card-word")
        browser.press(*ARROW_UP)
        browser.press(*ARROW_RIGHT)
        browser.wait(
            f"document.getElementById('card-word').textContent!=={json.dumps(current)}"
            " || !document.getElementById('memorize-summary').hidden"
        )
    check("카드를 모두 외움", browser.wait("!document.getElementById('memorize-summary').hidden"))

    browser.go(f"{base}/tests")
    browser.wait("!document.getElementById('test-start').disabled")
    browser.fill(count="2")
    browser.submit("test-start-form")
    check("시험 시작", browser.wait("/^\\/tests\\/\\d+$/.test(location.pathname)"))
    browser.wait("getComputedStyle(document.getElementById('question-area')).display!=='none'")
    browser.js("window.confirm=()=>true")
    browser.click("next-question")
    browser.wait("document.getElementById('next-question').textContent==='제출'")
    browser.click("next-question")
    check("제출 후 결과", browser.wait("getComputedStyle(document.getElementById('test-result')).display!=='none'"))
    browser.go(f"{base}/tests/history")
    check("시험 기록 표시", browser.js("document.querySelectorAll('#history-table tbody tr').length") == 1)
    check("375px 폭에 가로 스크롤 없음", browser.js("document.documentElement.scrollWidth<=document.documentElement.clientWidth"))
    browser.shot("demo_history_375.png")
    check("로그아웃", session.log_out())
    check("처리되지 않은 스크립트 오류 없음", not browser.script_errors, browser.script_errors)


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print("사용법: demo_check.py https://시연주소")
        return 2
    work_dir = Path(tempfile.mkdtemp(prefix="smart-voca-demo-check-"))
    report = Report()
    try:
        run(sys.argv[1].rstrip("/"), work_dir, report)
    finally:
        print(f"{sum(report.results)}/{len(report.results)} 통과", flush=True)
        print(f"결과 폴더: {work_dir}", flush=True)
    return 0 if report.results and all(report.results) else 1


if __name__ == "__main__":
    sys.exit(main())

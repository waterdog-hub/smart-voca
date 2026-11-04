#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 실제 서버와 헤드리스 브라우저로 화면 흐름을 점검한다 (테스트 정의서 §4)
# 파일 위치: ai-agent/scripts/browser_check.py
#
# 실행 (프로젝트 루트): .venv\Scripts\python ai-agent/scripts/browser_check.py
# 자동 테스트는 자바스크립트를 실행하지 않으므로, 화면 동작은 이 도구로 마일스톤마다 확인한다.
# 임시 폴더의 DB만 쓴다. data/words.csv는 가져오기 입력으로 읽기만 한다.

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from browser_check_lib import (
    TEST_PASSWORD,
    Browser,
    Report,
    Session,
    find_browser,
    free_port,
    wait_for_url,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_WORDS = PROJECT_ROOT / "data" / "words.csv"
PHONE_WIDTH = 375
DESKTOP_WIDTH = 1280


def check_auth_flow(session: Session) -> None:
    """가입, 로그인, 이메일 인증, 로그아웃 (테스트 정의서 §4.1)."""
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-auth@example.com"
    browser.resize(PHONE_WIDTH, 720, mobile=True)

    browser.go(f"{base}/")
    check("로그인 없이 홈을 열면 로그인 화면으로 이동", browser.js("location.pathname") == "/login")

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
    browser.go(f"{base}/")
    check("로그아웃 후 회원 화면 차단", browser.js("location.pathname") == "/login")


def _word_rows(browser: Browser) -> int:
    return browser.js("document.querySelectorAll('#word-rows tr').length")


def _first_word(browser: Browser) -> str | None:
    return browser.js("document.querySelector('#word-rows td[data-label=\"단어\"]')?.textContent")


def _list_settled(browser: Browser) -> bool:
    time.sleep(0.15)
    return browser.wait("document.getElementById('word-table-area').getAttribute('aria-busy')==='false'")


def _search(browser: Browser, keyword: str) -> None:
    browser.js(
        "const box=document.getElementById('word-search');"
        f"box.value={json.dumps(keyword)};box.dispatchEvent(new Event('input',{{bubbles:true}}))"
    )
    time.sleep(0.5)
    _list_settled(browser)


def _add_word(browser: Browser, word: str, meaning: str) -> None:
    browser.wait("!document.querySelector('#add-form button').disabled")
    browser.fill(add_dash_word=word, add_dash_meaning=meaning)
    browser.submit("add-form")


def check_words_flow(session: Session, work_dir: Path) -> None:
    """단어장과 공통 화면 (테스트 정의서 §4.2, §4.3)."""
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-words@example.com"
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)

    browser.go(f"{base}/words")
    check("로그인 없이 단어장을 열면 로그인 화면으로 이동", browser.js("location.pathname") == "/login")

    session.sign_up(email, "단어장")
    session.log_in(email)
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("인증 전 안내 띠 표시", browser.js("!!document.getElementById('verify-banner')"))
    check(
        "인증 전 쓰기 버튼은 비활성으로 표시",
        browser.js("document.getElementById('import-button').getAttribute('aria-disabled')==='true'"),
    )
    _add_word(browser, "blocked", "차단")
    check("인증 전 추가는 안내만 표시", browser.wait("document.getElementById('message').textContent.includes('이메일 인증')"))
    check("인증 전 단어가 추가되지 않음", not browser.js("document.getElementById('word-empty').hidden"))

    browser.go(session.verification_link(email))
    browser.wait("document.getElementById('verify-status').textContent.includes('완료')")
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("인증 후 안내 띠 사라짐", browser.js("!document.getElementById('verify-banner')"))
    check("빈 단어장 안내", "CSV" in browser.text("word-empty-text"))
    check("빈 단어장에서 표 숨김", browser.js("document.getElementById('word-table-area').hidden"))

    _add_word(browser, "apple", "사과/애플")
    check("단어 추가", browser.wait("document.querySelectorAll('#word-rows tr').length===1"))
    _add_word(browser, "APPLE", "x")
    check(
        "대소문자만 다른 중복은 칸 아래에 오류 표시",
        browser.wait(
            "!document.getElementById('add-word-error').hidden"
            " && document.getElementById('add-word-error').textContent.includes('apple')"
        ),
    )
    html_word = "<img src=x onerror=window.__xss=1>"
    _add_word(browser, html_word, html_word)
    browser.wait("document.querySelectorAll('#word-rows tr').length===2")
    time.sleep(0.3)
    check(
        "단어의 HTML이 실행되지 않고 글자로 표시",
        browser.js(
            "!window.__xss && !document.querySelector('#word-rows img')"
            " && document.getElementById('word-rows').textContent.includes('<img')"
        ),
    )

    browser.upload("import-file", SAMPLE_WORDS)
    check(
        "표본 단어장 가져오기 결과 표시",
        browser.wait("!document.getElementById('import-result').hidden", timeout=30),
        browser.text("message"),
    )
    sample_rows = list(csv.reader(io.StringIO(SAMPLE_WORDS.read_text(encoding="utf-8-sig"), newline="")))[1:]
    sample_keys = {row[0].strip().lower() for row in sample_rows}
    summary = browser.text("import-summary")
    check("가져온 개수가 파일과 일치", f"추가 {len(sample_keys - {'apple'})}개" in summary, summary)
    _list_settled(browser)
    expected_total = len(sample_keys | {"apple", html_word.lower()})
    check("전체 개수 표시", browser.text("word-total") == f"총 {expected_total:,}개", browser.text("word-total"))
    check("한 페이지에 50행", _word_rows(browser) == 50, _word_rows(browser))
    browser.shot("words_1280.png")

    logout_visible = (
        "(()=>{const box=document.getElementById('logout-button').getBoundingClientRect();"
        "return box.top>=0&&box.bottom<=window.innerHeight})()"
    )
    check("긴 목록의 맨 위에서 로그아웃 버튼이 보임", browser.js(logout_visible))
    browser.js("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(0.2)
    check("스크롤한 뒤에도 로그아웃 버튼이 보임", browser.js(logout_visible))
    browser.js("window.scrollTo(0, 0)")

    browser.click("page-next")
    _list_settled(browser)
    check("다음 페이지 이동", browser.text("page-info") == "51~100", browser.text("page-info"))
    browser.click("page-prev")
    _list_settled(browser)

    before_sort = _first_word(browser)
    browser.js("document.querySelector('th[data-sort=word] .sort-button').click()")
    _list_settled(browser)
    check(
        "열 제목을 다시 누르면 역순",
        browser.js("document.querySelector('th[data-sort=word]').getAttribute('aria-sort')") == "descending",
    )
    check("정렬 후 첫 단어가 바뀜", _first_word(browser) != before_sort)
    browser.js("document.querySelector('th[data-sort=created] .sort-button').click()")
    _list_settled(browser)
    check("등록일 정렬은 추가한 순서", _first_word(browser) == "apple", _first_word(browser))
    browser.js("document.querySelector('th[data-sort=word] .sort-button').click()")
    _list_settled(browser)

    _search(browser, "애플")
    check("뜻으로 검색", _first_word(browser) == "apple", _first_word(browser))
    _search(browser, "%%없는말%%")
    check("검색 결과 없음 안내", "검색 결과" in browser.text("word-empty-text"))
    _search(browser, "apple")

    browser.js("document.querySelector('.edit-col button').click()")
    check(
        "수정 패널이 열리고 첫 칸에 포커스",
        browser.js("!document.getElementById('edit-panel').hidden && document.activeElement.id==='edit-word'"),
    )
    browser.shot("words_edit_1280.png")
    browser.fill(edit_dash_word="Apple", edit_dash_meaning="사과 / 애플 / 회사")
    browser.submit("edit-form")
    check(
        "수정 저장과 뜻 정리",
        browser.wait(
            "document.querySelector('#word-rows td[data-label=\"뜻\"]')?.textContent==='사과/애플/회사'"
            " && document.getElementById('edit-panel').hidden"
        ),
    )
    browser.js("document.querySelector('.edit-col button').click()")
    browser.js("document.getElementById('edit-word').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
    check(
        "Esc로 닫으면 포커스가 돌아옴",
        browser.js("document.getElementById('edit-panel').hidden && document.activeElement.classList.contains('needs-verified')"),
    )

    browser.js("document.querySelector('#word-rows input[type=checkbox]').click()")
    check("선택 삭제 버튼에 개수 표시", browser.text("delete-selected") == "선택 삭제 (1)", browser.text("delete-selected"))
    browser.js("window.confirm=()=>false; document.getElementById('delete-selected').click()")
    time.sleep(0.3)
    check("삭제 확인을 취소하면 단어 유지", _first_word(browser) == "Apple", _first_word(browser))
    browser.js("window.confirm=()=>true; document.getElementById('delete-selected').click()")
    check("삭제 확인 후 안내", browser.wait("document.getElementById('message').textContent.includes('1개를 삭제')"), browser.text("message"))
    _list_settled(browser)
    check("삭제 후 선택 해제", browser.js("document.getElementById('delete-selected').disabled"))
    check("삭제한 단어가 목록에서 사라짐", _first_word(browser) != "Apple", _first_word(browser))

    _search(browser, "")
    export_head = browser.js(
        "fetch('/api/v1/words/export').then(r=>r.arrayBuffer())"
        ".then(b=>Array.from(new Uint8Array(b).slice(0,8)).join(','))"
    )
    check("내보내기 파일이 BOM과 머리글로 시작", export_head == "239,187,191,119,111,114,100,44", export_head)

    browser.resize(PHONE_WIDTH, 800, mobile=True)
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("375px 폭에서 가로 스크롤 없음", browser.js("document.documentElement.scrollWidth<=window.innerWidth"))
    check("375px 폭에서 표가 카드로 바뀜", browser.js("getComputedStyle(document.querySelector('#word-rows tr')).display") == "grid")
    browser.shot("words_375.png")

    browser.resize(DESKTOP_WIDTH, 900, mobile=False)
    browser.go(f"{base}/words")
    _list_settled(browser)
    bad_file = work_dir / "bad_header.csv"
    bad_file.write_text("wrong,header\na,b\n", encoding="utf-8")
    browser.upload("import-file", bad_file)
    check("첫 줄이 틀린 파일은 안내", browser.wait("document.getElementById('message').textContent.includes('word,meaning')"), browser.text("message"))
    check("단어장 화면에서 로그아웃", session.log_out())


def run_checks(work_dir: Path, report: Report) -> None:
    app_port, debug_port = free_port(), free_port()
    base_url = f"http://127.0.0.1:{app_port}"
    environment = {
        **os.environ,
        "APP_ENV": "local",
        "DATABASE_URL": f"sqlite:///{(work_dir / 'browser_check.db').as_posix()}",
        "PUBLIC_BASE_URL": base_url,
        # 서버 출력을 UTF-8로 고정해 한글 Windows에서도 메일 로그를 같은 방식으로 읽는다
        "PYTHONIOENCODING": "utf-8",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
    )
    log_path = work_dir / "server.log"
    with open(log_path, "wb") as server_log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "--factory", "web.app:create_app", "--app-dir", "src", "--port", str(app_port)],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=server_log,
            stderr=subprocess.STDOUT,
        )
        browser_process = subprocess.Popen(
            [
                find_browser(),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={work_dir / 'browser_profile'}",
                "about:blank",
            ]
        )
        try:
            wait_for_url(f"{base_url}/healthz")
            wait_for_url(f"http://127.0.0.1:{debug_port}/json/version")
            new_tab = urllib.request.Request(f"http://127.0.0.1:{debug_port}/json/new", method="PUT")
            with urllib.request.urlopen(new_tab) as response:
                debug_url = json.load(response)["webSocketDebuggerUrl"]
            browser = Browser(debug_url, work_dir)
            session = Session(base_url, browser, report, log_path)
            check_auth_flow(session)
            check_words_flow(session, work_dir)
            report.check("처리되지 않은 스크립트 오류 없음", not browser.script_errors, browser.script_errors)
        finally:
            server.terminate()
            browser_process.terminate()
            server.wait(10)
            browser_process.wait(10)
    server_errors = re.findall(r"Traceback|\" 500 ", log_path.read_bytes().decode("utf-8", "replace"))
    report.check("서버 오류 없음", not server_errors, f"{len(server_errors)}건")


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 서버와 헤드리스 브라우저로 화면 흐름을 점검합니다.")
    parser.add_argument("--keep", action="store_true", help="스크린샷과 서버 로그가 든 임시 폴더를 남깁니다.")
    arguments = parser.parse_args()
    # 한글 Windows 콘솔에서도 결과 출력 때문에 점검이 멈추지 않게 한다
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    work_dir = Path(tempfile.mkdtemp(prefix="smart-voca-browser-"))
    report = Report()
    try:
        run_checks(work_dir, report)
    finally:
        print(f"{sum(report.results)}/{len(report.results)} 통과", flush=True)
        if arguments.keep:
            print(f"결과 폴더: {work_dir}", flush=True)
        else:
            shutil.rmtree(work_dir, ignore_errors=True)
    return 0 if report.results and all(report.results) else 1


if __name__ == "__main__":
    sys.exit(main())

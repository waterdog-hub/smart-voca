#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 단어장과 화면 공통 점검 (테스트 정의서 §4)
# 파일 위치: ai-agent/scripts/browser_checks_words.py

import csv
import io
import json
import time
from pathlib import Path

from browser_check_lib import Browser, DESKTOP_WIDTH, PHONE_WIDTH, Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_WORDS = PROJECT_ROOT / "data" / "words.csv"


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

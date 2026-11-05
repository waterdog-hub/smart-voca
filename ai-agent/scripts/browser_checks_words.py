#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 단어장 고르기와 내 단어 화면 점검 (테스트 정의서 §4, 결정 D-WB08)
# 파일 위치: ai-agent/scripts/browser_checks_words.py
#
# 점검용 단어장(작은 것 4개)은 browser_check.py가 임시 DB에 넣는다. 실제 표본 단어장은
# data/wordbooks.json 그대로 쓴다. 다른 점검 파일은 add_wordbook으로 단어를 준비한다.

import csv
import io
import json
import time
from pathlib import Path

from browser_check_lib import DESKTOP_WIDTH, PHONE_WIDTH, Browser, Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_WORDS = PROJECT_ROOT / "data" / "words.csv"
SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "wordbooks.json"
SAMPLE_BOOK_TITLE = "기본 영단어 1"
SAMPLE_BOOK_ROWS = 500

GREEK_TITLE = "점검용 그리스 문자"
GREEK_MORE_TITLE = "점검용 그리스 문자 추가"
OVERLAP_TITLE = "점검용 겹침"
HTML_TITLE = "점검용 HTML"
HTML_WORD = "<img src=x onerror=window.__xss=1>"
# (slug, 제목, 단어와 뜻). 다른 점검 파일이 단어 값을 그대로 기대하므로 함부로 바꾸지 않는다
CHECK_WORDBOOKS = (
    ("check-greek", GREEK_TITLE, (("alpha", "첫째"), ("bravo", "둘째"), ("charlie", "셋째"))),
    ("check-greek-more", GREEK_MORE_TITLE, (("delta", "넷째"), ("<b>echo</b>", "<i>다섯째"))),
    # the는 표본 단어장 1에도 있어 겹치는 단어 처리를 확인한다
    ("check-overlap", OVERLAP_TITLE, (("the", "정관사"), ("zebra", "얼룩말"))),
    ("check-html", HTML_TITLE, ((HTML_WORD, HTML_WORD),)),
)


def write_check_wordbooks(directory: Path) -> Path:
    """점검용 단어장 CSV와 목록 파일을 만들고 목록 파일 경로를 돌려준다."""
    directory.mkdir(parents=True, exist_ok=True)
    items = []
    for slug, title, rows in CHECK_WORDBOOKS:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["word", "meaning"])
        writer.writerows(rows)
        (directory / f"{slug}.csv").write_text(buffer.getvalue(), encoding="utf-8")
        items.append(
            {"slug": slug, "title": title, "description": "화면 점검용 단어장", "source_note": "점검 도구", "file": f"{slug}.csv"}
        )
    manifest = directory / "wordbooks.json"
    manifest.write_text(json.dumps({"wordbooks": items}, ensure_ascii=False), encoding="utf-8")
    return manifest


def _card_by_title(title: str) -> str:
    # h2의 첫 글자 노드가 제목이다. 담은 단어장에는 뒤에 배지가 붙는다
    return (
        "[...document.querySelectorAll('.wordbook-card')]"
        f".find(card=>card.querySelector('h2').firstChild.textContent.trim()==={json.dumps(title)})"
    )


def _cards_ready(browser: Browser) -> bool:
    return browser.wait(
        "document.getElementById('wordbook-list').getAttribute('aria-busy')==='false'"
        " && document.querySelectorAll('.wordbook-card').length>0"
    )


def _click_card_button(browser: Browser, title: str) -> None:
    browser.js(f"{_card_by_title(title)}.querySelector('button').click()")


def add_wordbook(browser: Browser, base: str, title: str) -> bool:
    """단어장 화면에서 제목이 같은 단어장을 담는다. 담았다는 안내가 나오면 True다."""
    browser.go(f"{base}/wordbooks")
    _cards_ready(browser)
    _click_card_button(browser, title)
    return _message_has(browser, f"'{title}' 단어장을 담았습니다")


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


def _sample_rows() -> list[tuple[str, str]]:
    text = SAMPLE_WORDS.read_text(encoding="utf-8-sig")
    rows = [row for row in csv.reader(io.StringIO(text, newline=""))][1:]
    return [(row[0].strip(), row[1].strip()) for row in rows if row][:SAMPLE_BOOK_ROWS]


def _message_has(browser: Browser, text: str) -> bool:
    return browser.wait(f"document.getElementById('message').textContent.includes({json.dumps(text)})")


def check_words_flow(session: Session) -> None:
    """단어장 고르기, 내 단어, 공통 화면 (테스트 정의서 §4.2, §4.3)."""
    browser, check, base = session.browser, session.report.check, session.base
    email = "browser-words@example.com"
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)

    for path in ("/wordbooks", "/words"):
        browser.go(f"{base}{path}")
        check(f"로그인 없이 {path}를 열면 로그인 화면으로 이동", browser.js("location.pathname") == "/login")

    session.sign_up(email, "단어장")
    session.log_in(email)
    browser.go(f"{base}/wordbooks")
    _cards_ready(browser)
    book_count = len(json.loads(SAMPLE_MANIFEST.read_text("utf-8"))["wordbooks"]) + len(CHECK_WORDBOOKS)
    check("준비된 단어장이 모두 카드로 표시", browser.js("document.querySelectorAll('.wordbook-card').length") == book_count)
    sample_card_text = browser.js(f"{_card_by_title(SAMPLE_BOOK_TITLE)}.textContent")
    check("카드에 단어 수와 예시 단어와 출처 표시", all(part in sample_card_text for part in ("단어 500개", "예: the", "출처:")), sample_card_text)
    check("담은 단어장이 없다고 요약", "담은 단어장 0개" in browser.text("wordbook-summary"), browser.text("wordbook-summary"))
    check("인증 전 안내 띠 표시", browser.js("!!document.getElementById('verify-banner')"))
    check(
        "인증 전 담기 버튼은 비활성으로 표시",
        browser.js(f"{_card_by_title(SAMPLE_BOOK_TITLE)}.querySelector('button').getAttribute('aria-disabled')==='true'"),
    )
    _click_card_button(browser, SAMPLE_BOOK_TITLE)
    check("인증 전 담기는 안내만 표시", _message_has(browser, "이메일 인증"))
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("인증 전에는 단어가 담기지 않음", not browser.js("document.getElementById('word-empty').hidden"))

    browser.go(session.verification_link(email))
    browser.wait("document.getElementById('verify-status').textContent.includes('완료')")
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("인증 후 안내 띠 사라짐", browser.js("!document.getElementById('verify-banner')"))
    check("담은 단어가 없으면 단어장 고르기 안내", "단어장" in browser.text("word-empty-text"))
    check("빈 목록에서 표 숨김", browser.js("document.getElementById('word-table-area').hidden"))
    check("빈 목록에 단어장 이동 링크 표시", browser.js("!document.getElementById('word-empty-link').hidden"))

    # 담기
    browser.go(f"{base}/wordbooks")
    _cards_ready(browser)
    _click_card_button(browser, SAMPLE_BOOK_TITLE)
    check(
        "단어장 담기 결과 안내",
        _message_has(browser, f"'{SAMPLE_BOOK_TITLE}' 단어장을 담았습니다. 새 단어 {SAMPLE_BOOK_ROWS}개"),
        browser.text("message"),
    )
    check(
        "담은 카드에 배지와 제외 버튼 표시",
        browser.wait(
            f"(()=>{{const card={_card_by_title(SAMPLE_BOOK_TITLE)};"
            "return !!card&&card.dataset.added==='true'&&!!card.querySelector('.wordbook-badge')"
            "&&card.querySelector('button').textContent==='제외'})()"
        ),
    )
    check("담은 단어장 수 요약 갱신", "담은 단어장 1개" in browser.text("wordbook-summary"), browser.text("wordbook-summary"))
    browser.shot("wordbooks_1280.png")

    # 내 단어: 목록, 페이지, 정렬, 검색
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("담은 단어 전체 개수 표시", browser.text("word-total") == f"총 {SAMPLE_BOOK_ROWS:,}개", browser.text("word-total"))
    check("한 페이지에 50행", _word_rows(browser) == 50, _word_rows(browser))
    check("수정·삭제·가져오기 같은 쓰기 조작이 없음", browser.js("!document.querySelector('#word-rows button, #word-rows input, .edit-col, #add-form')"))
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

    sample_rows = _sample_rows()
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
    check("등록일 정렬은 담긴 순서", _first_word(browser) == sample_rows[0][0], _first_word(browser))
    browser.js("document.querySelector('th[data-sort=word] .sort-button').click()")
    _list_settled(browser)

    needle = sample_rows[1][1]
    matches = sorted(
        (word for word, meaning in sample_rows if needle.lower() in word.lower() or needle.lower() in meaning.lower()),
        key=str.lower,
    )
    _search(browser, needle)
    check("뜻으로 검색", _first_word(browser) == matches[0], f"{_first_word(browser)} != {matches[0]}")
    _search(browser, "%%없는말%%")
    check("검색 결과 없음 안내", "검색 결과" in browser.text("word-empty-text"))
    check("검색 결과가 없을 때는 단어장 이동 링크를 숨김", browser.js("document.getElementById('word-empty-link').hidden"))
    _search(browser, "")

    # 겹치는 단어와 제외
    browser.go(f"{base}/wordbooks")
    _cards_ready(browser)
    _click_card_button(browser, OVERLAP_TITLE)
    check(
        "이미 있는 단어는 건너뛴다고 안내",
        _message_has(browser, "새 단어 1개, 이미 있던 단어 1개는 건너뜀"),
        browser.text("message"),
    )
    browser.js("window.confirm=()=>false")
    _click_card_button(browser, SAMPLE_BOOK_TITLE)
    time.sleep(0.3)
    check(
        "제외 확인을 취소하면 담은 상태 유지",
        browser.js(f"{_card_by_title(SAMPLE_BOOK_TITLE)}.dataset.added") == "true",
    )
    browser.js("window.confirm=()=>true")
    _click_card_button(browser, SAMPLE_BOOK_TITLE)
    check(
        "제외하면 겹치는 단어는 남긴다고 안내",
        _message_has(browser, f"학습에서 빠진 단어 {SAMPLE_BOOK_ROWS - 1}개, 다른 단어장에도 있어 남긴 단어 1개"),
        browser.text("message"),
    )
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("남은 단어는 겹친 단어와 새 단어", browser.text("word-total") == "총 2개", browser.text("word-total"))
    check(
        "먼저 담은 뜻이 유지됨",
        browser.js("document.querySelector('#word-rows td[data-label=\"뜻\"]')?.textContent") == sample_rows[0][1],
    )

    # HTML이 섞인 단어
    add_wordbook(browser, base, HTML_TITLE)
    browser.go(f"{base}/words")
    _list_settled(browser)
    _search(browser, "img")
    check("검색 결과에 HTML 단어 표시", _word_rows(browser) == 1, _word_rows(browser))
    time.sleep(0.3)
    check(
        "단어의 HTML이 실행되지 않고 글자로 표시",
        browser.js(
            "!window.__xss && !document.querySelector('#word-rows img')"
            " && document.getElementById('word-rows').textContent.includes('<img')"
        ),
    )
    _search(browser, "")

    # 좁은 화면
    browser.resize(PHONE_WIDTH, 800, mobile=True)
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("375px 폭 내 단어에 가로 스크롤 없음", browser.js("document.documentElement.scrollWidth<=window.innerWidth"))
    check("375px 폭에서 표가 카드로 바뀜", browser.js("getComputedStyle(document.querySelector('#word-rows tr')).display") == "grid")
    browser.shot("words_375.png")
    browser.go(f"{base}/wordbooks")
    _cards_ready(browser)
    check("375px 폭 단어장 화면에 가로 스크롤 없음", browser.js("document.documentElement.scrollWidth<=window.innerWidth"))
    browser.shot("wordbooks_375.png")
    browser.resize(DESKTOP_WIDTH, 900, mobile=False)

    # 모두 제외하면 빈 목록
    browser.go(f"{base}/wordbooks")
    _cards_ready(browser)
    browser.js("window.confirm=()=>true")
    for title in (OVERLAP_TITLE, HTML_TITLE):
        _click_card_button(browser, title)
        check(f"'{title}' 제외", _message_has(browser, f"'{title}' 단어장을 제외했습니다"), browser.text("message"))
        browser.wait(f"{_card_by_title(title)}.dataset.added==='false'")
    check("모두 제외하면 담은 단어장 0개", "담은 단어장 0개" in browser.text("wordbook-summary"), browser.text("wordbook-summary"))
    browser.go(f"{base}/words")
    _list_settled(browser)
    check("모두 제외하면 단어장 고르기 안내", "담은 단어가 없습니다" in browser.text("word-empty-text"))
    check("단어장 화면에서 로그아웃", session.log_out())

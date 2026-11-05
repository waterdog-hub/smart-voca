#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 발표용 화면 캡처(PC·휴대폰)와 시연 영상의 프레임을 만든다
# 파일 위치: ai-agent/claude/261104_웹서비스 전환/script/capture_presentation_assets.py
#
# 실행 (프로젝트 루트, 프로젝트 가상환경): .venv\Scripts\python "ai-agent/claude/261104_웹서비스 전환/script/capture_presentation_assets.py" 출력폴더
# 임시 DB에 예시 회원("민지")과 학습 데이터를 만들고 임시 서버와 헤드리스 브라우저로 화면을 찍는다. 개발 DB는 건드리지 않는다.
# 결과: 출력폴더/screens/*.png (캡처), 출력폴더/frames/*.jpg와 frames.json (영상 재료, make_video.py가 mp4로 만든다)
# --video-only를 붙이면 캡처는 건너뛰고 영상 재료만 다시 만든다

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "ai-agent" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from browser_check_lib import Browser, find_browser, free_port, wait_for_url  # noqa: E402

PASSWORD = "preview long passphrase 1"
RICH = ("rich@example.com", "민지")
VIDEO = ("video@example.com", "보카친구")
THEMES = ("peach", "lavender", "mint", "sky", "lemon", "cocoa")
PC_SIZE = (1280, 720)
PHONE_SIZE = (375, 812)
VIDEO_FPS_CAPTURE_QUALITY = 74


# ── 예시 데이터 ────────────────────────────────────────────────
class _Mailer:
    def __init__(self):
        self.last = None

    def send(self, message):
        self.last = message


def seed(database_url: str) -> None:
    """임시 DB에 회원 두 명을 만든다. 민지는 진도와 시험 기록이 있고, 보카친구는 비어 있다(영상용)."""
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from web.app import create_app
    from web.db.tables import TestAttemptItem
    from web.settings import Settings

    mailer = _Mailer()
    settings = Settings(app_env="local", database_url=database_url, _env_file=None)
    api = "/api/v1"
    with TestClient(create_app(settings, mailer=mailer), base_url="http://testserver") as root_client:
        factory = root_client.app.state.session_factory

        def member(email: str, name: str) -> TestClient:
            client = TestClient(root_client.app, base_url="http://testserver")
            client.post(f"{api}/auth/signup", json={"email": email, "password": PASSWORD, "display_name": name,
                                                    "terms_agreed": True, "privacy_agreed": True}).raise_for_status()
            token = re.search(r"#token=(\S+)", mailer.last.body).group(1)
            client.post(f"{api}/auth/verify-email", json={"token": token}).raise_for_status()
            return client

        def login(client: TestClient, email: str) -> dict:
            response = client.post(f"{api}/auth/login", json={"email": email, "password": PASSWORD})
            response.raise_for_status()
            return {"X-CSRF-Token": response.json()["csrf_token"]}

        for email, name in (RICH, VIDEO):
            member(email, name)  # 가입 제한(같은 주소 1분)을 피하려고 서로 다른 주소를 쓴다
        client = TestClient(root_client.app, base_url="http://testserver")
        headers = login(client, RICH[0])
        books = client.get(f"{api}/wordbooks").json()["items"]
        client.post(f"{api}/wordbooks/{books[0]['id']}/add", headers=headers).raise_for_status()
        client.post(f"{api}/plans", headers=headers).raise_for_status()
        for item in client.get(f"{api}/plans/1").json()["items"]:
            client.patch(f"{api}/plan-items/{item['id']}", json={"done": True}, headers=headers).raise_for_status()
        client.post(f"{api}/plans", headers=headers).raise_for_status()
        day_two = client.get(f"{api}/plans/2").json()["items"]
        for item in day_two[: len(day_two) * 2 // 5]:
            client.patch(f"{api}/plan-items/{item['id']}", json={"done": True}, headers=headers).raise_for_status()

        for wrong_count in (1, 3, 0):  # 시험 기록 세 줄
            started = client.post(f"{api}/tests", headers=headers,
                                  json={"test_format": "multiple", "test_direction": "en_ko", "count": 10})
            started.raise_for_status()
            attempt = started.json()
            with factory() as db:
                rows = {row.id: row for row in db.scalars(select(TestAttemptItem).where(TestAttemptItem.attempt_id == attempt["id"]))}
            answers = []
            for index, item in enumerate(attempt["items"]):
                correct = rows[item["id"]].correct_index
                answers.append({"item_id": item["id"], "answer": (correct + 1) % 4 if index < wrong_count else correct})
            client.post(f"{api}/tests/{attempt['id']}/submit", json={"answers": answers}, headers=headers).raise_for_status()


# ── 서버와 브라우저 ────────────────────────────────────────────
class Session:
    def __init__(self, base: str, browser: Browser, database_path: Path) -> None:
        self.base = base
        self.browser = browser
        self.database_path = database_path
        self.frames: list[tuple[float, bytes]] = []
        self.started = time.monotonic()
        self.cursor = (640, 400)

    # 로그인과 화면 크기
    def viewport(self, width: int, height: int, mobile: bool, scale: float = 2) -> None:
        self.browser.call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                          deviceScaleFactor=scale, mobile=mobile)

    def log_in(self, email: str) -> None:
        b = self.browser
        b.go(f"{self.base}/login")
        b.fill(email=email, password=PASSWORD)
        b.submit("login-form")
        b.wait("location.pathname==='/' && !!document.getElementById('logout-button')")
        b.ready()

    def log_out(self) -> None:
        self.browser.click("logout-button")
        self.browser.wait("location.pathname==='/login'")

    def shot(self, directory: Path, name: str) -> None:
        import base64
        time.sleep(0.5)  # 글꼴과 그림이 그려질 시간
        data = self.browser.call("Page.captureScreenshot", format="png")["data"]
        (directory / name).write_bytes(base64.b64decode(data))
        print("  ", name, flush=True)

    # 영상: 화면을 연속으로 찍어 모은다
    def grab(self) -> None:
        import base64
        try:
            data = self.browser.call("Page.captureScreenshot", format="jpeg", quality=VIDEO_FPS_CAPTURE_QUALITY).get("data")
        except (TimeoutError, OSError):
            data = None
        if not data:
            # 화면이 바뀌는 중에는 브라우저가 응답하지 않거나 오류를 줄 수 있다. 그 프레임은 건너뛴다
            time.sleep(0.05)
            return
        self.frames.append((time.monotonic() - self.started, base64.b64decode(data)))

    def hold(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.grab()

    def inject_cursor(self) -> None:
        x, y = self.cursor
        script = """(()=>{const old=document.getElementById('fake-cursor'); if(old) old.remove();
            const c=document.createElement('div'); c.id='fake-cursor';
            c.style.cssText='position:fixed;z-index:99999;width:46px;height:46px;pointer-events:none;'
              +'background:url(/static/cursor-paw-click.svg) center/contain no-repeat;'
              +'transition:left .55s ease,top .55s ease,transform .15s;transform:translate(-50%,-50%) scale(1.3);'
              +'left:__X__px;top:__Y__px';
            document.body.appendChild(c);
            window.__moveTo=(sel)=>{const e=document.querySelector(sel); if(!e) return null;
              const r=e.getBoundingClientRect(); c.style.left=(r.left+r.width/2)+'px'; c.style.top=(r.top+r.height/2)+'px';
              return [r.left+r.width/2, r.top+r.height/2];};
            window.__press=()=>{c.style.transform='translate(-50%,-50%) scale(1)';
              setTimeout(()=>{c.style.transform='translate(-50%,-50%) scale(1.3)'},200);};})()"""
        self.browser.js(script.replace("__X__", str(int(x))).replace("__Y__", str(int(y))))

    def after_load(self, seconds: float = 0.8) -> None:
        self.browser.ready()
        self.inject_cursor()
        self.hold(seconds)

    def click(self, selector: str, hold_after: float = 0.6) -> None:
        """커서가 대상으로 움직여 누르는 모습을 찍은 뒤 실제로 누른다."""
        b = self.browser
        print("   누르기:", selector, flush=True)
        position = b.js(f"window.__moveTo({json.dumps(selector)})")
        if position:
            self.cursor = (position[0], position[1])
        self.hold(0.75)
        b.js("window.__press()")
        self.hold(0.2)
        b.js(f"document.querySelector({json.dumps(selector)}).click()")
        self.hold(hold_after)

    def correct_choice(self, question: str) -> int:
        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "select correct_index from test_attempt_items where question=? order by id desc limit 1", (question,)
            ).fetchone()
        finally:
            connection.close()
        return int(row[0])


def screens(session: Session, directory: Path) -> None:
    b = session.browser
    base = session.base
    directory.mkdir(parents=True, exist_ok=True)
    # PC
    session.viewport(*PC_SIZE, mobile=False)
    b.go(f"{base}/")
    session.shot(directory, "01_pc_landing.png")
    session.log_in(RICH[0])
    session.shot(directory, "02_pc_home.png")
    b.go(f"{base}/wordbooks")
    b.wait("document.querySelectorAll('.wordbook-card').length>0")
    session.shot(directory, "03_pc_wordbooks.png")
    b.go(f"{base}/memorize")
    b.wait("!document.getElementById('memorize-card').hidden")
    b.click("show-meaning")
    b.wait("!document.getElementById('card-actions').hidden")
    session.shot(directory, "04_pc_memorize.png")
    # 시험 결과: 문제마다 정답 4개 이상, 하나는 일부러 틀린다
    b.go(f"{base}/tests")
    b.wait("!document.getElementById('test-start').disabled")
    b.fill(count="5")
    b.submit("test-start-form")
    b.wait("/^\\/tests\\/\\d+$/.test(location.pathname)")
    b.wait("getComputedStyle(document.getElementById('question-area')).display!=='none'")
    b.js("window.confirm=()=>true")
    for number in range(5):
        question = b.text("question-text")
        correct = session.correct_choice(question)
        pick = correct if number != 3 else (correct + 1) % 4
        b.js(f"document.querySelectorAll('#choice-list .choice input')[{pick}].click()")
        time.sleep(0.15)
        b.click("next-question")
        time.sleep(0.3)
    b.wait("getComputedStyle(document.getElementById('test-result')).display!=='none'")
    session.shot(directory, "05_pc_test_result.png")
    b.go(f"{base}/tests/history")
    session.shot(directory, "06_pc_history.png")
    b.go(f"{base}/settings")
    b.js("document.querySelector('.theme-picker').scrollIntoView({block:'center'})")
    session.shot(directory, "07_pc_settings_theme.png")

    # 테마 6색 (홈 화면)
    b.go(f"{base}/")
    for theme in THEMES:
        b.js(f"document.documentElement.dataset.theme={json.dumps(theme)}")
        session.shot(directory, f"theme_{theme}.png")
    b.js("document.documentElement.dataset.theme='peach'")

    # 휴대폰
    session.viewport(*PHONE_SIZE, mobile=True)
    b.go(f"{base}/")
    session.shot(directory, "10_phone_home.png")
    b.js("document.getElementById('nav-more-button').click()")
    session.shot(directory, "11_phone_nav_more.png")
    b.go(f"{base}/tests/history")
    session.shot(directory, "12_phone_history.png")
    b.go(f"{base}/wordbooks")
    b.wait("document.querySelectorAll('.wordbook-card').length>0")
    session.shot(directory, "13_phone_wordbooks.png")
    b.go(f"{base}/memorize")
    b.wait("!document.getElementById('memorize-card').hidden")
    b.click("show-meaning")
    b.wait("!document.getElementById('card-actions').hidden")
    session.shot(directory, "14_phone_memorize.png")
    session.log_out()


def record_video(session: Session, directory: Path) -> None:
    """보카친구가 단어장을 담고, 암기하고, 시험을 보는 30초 남짓의 흐름을 찍는다."""
    b = session.browser
    base = session.base
    session.viewport(*PC_SIZE, mobile=False, scale=1)
    session.log_in(VIDEO[0])
    session.frames.clear()
    session.started = time.monotonic()
    session.cursor = (900, 500)
    session.after_load(2.0)  # 홈: 공부할 단어장을 먼저 담으세요
    session.click('.nav-primary a[href="/wordbooks"]', 0.2)
    session.after_load(1.0)
    b.wait("document.querySelectorAll('.wordbook-card button').length>0")
    session.after_load(0.3)
    session.click(".wordbook-card button", 2.0)  # 첫 단어장 담기
    session.click('.nav-primary a[href="/"]', 0.2)
    session.after_load(1.2)
    session.click("[data-create-plan]", 0.3)
    b.wait("location.pathname==='/memorize'", timeout=15)
    b.wait("!document.getElementById('memorize-card').hidden")
    session.after_load(1.0)
    for _ in range(3):
        session.click("#show-meaning", 0.9)
        b.wait("!document.getElementById('card-actions').hidden")
        session.click("#remember-button", 0.5)
    session.click('.nav-primary a[href="/tests"]', 0.2)
    session.after_load(0.8)
    b.wait("!document.getElementById('test-start').disabled")
    b.js("document.getElementById('count').value='3'")
    session.hold(0.5)
    session.click("#test-start", 0.3)
    b.wait("/^\\/tests\\/\\d+$/.test(location.pathname)", timeout=15)
    b.wait("getComputedStyle(document.getElementById('question-area')).display!=='none'")
    session.after_load(1.0)
    b.js("window.confirm=()=>true")  # 제출 확인 창이 떠서 화면 조작이 멈추지 않게 한다
    for number in range(3):
        question = b.text("question-text")
        correct = session.correct_choice(question)
        session.click(f"#choice-list .choice:nth-child({correct + 2})", 0.6)  # 첫 자식은 legend
        session.click("#next-question", 0.5)
    b.wait("getComputedStyle(document.getElementById('test-result')).display!=='none'")
    session.hold(3.5)
    frames_dir = directory / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.jpg"):
        old.unlink()
    index = []
    for number, (stamp, data) in enumerate(session.frames):
        name = f"frame_{number:05d}.jpg"
        (frames_dir / name).write_bytes(data)
        index.append({"file": name, "t": round(stamp, 3)})
    (directory / "frames.json").write_text(json.dumps(index), encoding="utf-8")
    print(f"   프레임 {len(index)}장, {index[-1]['t']:.1f}초", flush=True)


def main() -> int:
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(arguments) != 1:
        print("사용법: capture_presentation_assets.py 출력폴더 [--video-only]")
        return 2
    output = Path(arguments[0])
    work = Path(tempfile.mkdtemp(prefix="smart-voca-capture-"))
    database_path = work / "capture.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    app_port, debug_port = free_port(), free_port()
    base = f"http://127.0.0.1:{app_port}"
    environment = {**os.environ, "APP_ENV": "local", "DATABASE_URL": database_url,
                   "PUBLIC_BASE_URL": base, "PYTHONIOENCODING": "utf-8"}
    for command in ([sys.executable, "-m", "alembic", "upgrade", "head"],
                    [sys.executable, str(PROJECT_ROOT / "ai-agent" / "scripts" / "load_wordbooks.py")]):
        subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True, capture_output=True)
    print("예시 데이터를 만듭니다", flush=True)
    seed(database_url)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "--factory", "web.app:create_app", "--app-dir", "src", "--port", str(app_port)],
        cwd=PROJECT_ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = subprocess.Popen([find_browser(), "--headless=new", "--disable-gpu", "--no-first-run",
                               f"--remote-debugging-port={debug_port}", f"--user-data-dir={work / 'profile'}", "about:blank"])
    try:
        wait_for_url(f"{base}/healthz")
        wait_for_url(f"http://127.0.0.1:{debug_port}/json/version")
        request = urllib.request.Request(f"http://127.0.0.1:{debug_port}/json/new", method="PUT")
        with urllib.request.urlopen(request) as response:
            debug_url = json.load(response)["webSocketDebuggerUrl"]
        browser = Browser(debug_url, work)
        browser.socket.sock.settimeout(8.0)  # 응답이 멈추면 오류로 끝나게 한다
        session = Session(base, browser, database_path)
        if "--video-only" not in sys.argv:
            print("화면을 찍습니다", flush=True)
            screens(session, output / "screens")
        print("시연 영상을 찍습니다", flush=True)
        record_video(session, output)
    finally:
        server.terminate()
        chrome.terminate()
        server.wait(10)
        chrome.wait(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())

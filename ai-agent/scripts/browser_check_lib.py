#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 브라우저 점검 도구의 공용 부품 (브라우저 제어, 결과 기록, 서버 로그 읽기)
# 파일 위치: ai-agent/scripts/browser_check_lib.py
#
# 외부 패키지를 늘리지 않으려고 Chrome DevTools Protocol을 표준 라이브러리로 직접 호출한다.

import base64
import json
import os
import re
import secrets
import shutil
import socket
import struct
import time
import urllib.request
from pathlib import Path

BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
TEST_PASSWORD = "correct horse battery staple"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PHONE_WIDTH = 375
DESKTOP_WIDTH = 1280


class WebSocketClient:
    """브라우저 제어에 필요한 만큼만 구현한 WebSocket 클라이언트."""

    def __init__(self, url: str) -> None:
        match = re.match(r"ws://([^:/]+):(\d+)(/.*)", url)
        self.sock = socket.create_connection((match[1], int(match[2])))
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        self.sock.sendall(
            (
                f"GET {match[3]} HTTP/1.1\r\nHost: {match[1]}:{match[2]}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.sock.recv(1)

    def send(self, text: str) -> None:
        data = text.encode()
        mask = secrets.token_bytes(4)
        size = len(data)
        if size < 126:
            length = bytes([0x80 | size])
        elif size < 65536:
            length = bytes([0x80 | 126]) + struct.pack(">H", size)
        else:
            length = bytes([0x80 | 127]) + struct.pack(">Q", size)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.sock.sendall(b"\x81" + length + mask + masked)

    def _read_exact(self, size: int) -> bytes:
        buffer = b""
        while len(buffer) < size:
            chunk = self.sock.recv(size - len(buffer))
            if not chunk:
                raise EOFError("브라우저 연결이 끊겼습니다.")
            buffer += chunk
        return buffer

    def receive(self) -> str:
        payload = b""
        while True:
            first, second = self._read_exact(2)
            size = second & 0x7F
            if size == 126:
                size = struct.unpack(">H", self._read_exact(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._read_exact(8))[0]
            payload += self._read_exact(size)
            if first & 0x80:
                return payload.decode()


class Browser:
    def __init__(self, url: str, shots_dir: Path) -> None:
        self.socket = WebSocketClient(url)
        self.shots_dir = shots_dir
        self.next_id = 0
        self.script_errors: list[str] = []
        for domain in ("Page", "Runtime", "DOM"):
            self.call(f"{domain}.enable")

    def call(self, method: str, **params: object) -> dict:
        self.next_id += 1
        self.socket.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.socket.receive())
            if message.get("method") == "Runtime.exceptionThrown":
                self.script_errors.append(str(message["params"]["exceptionDetails"].get("text")))
            if message.get("id") == self.next_id:
                return message.get("result", {})

    def js(self, expression: str):
        result = self.call(
            "Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True
        )
        return result.get("result", {}).get("value")

    def wait(self, expression: str, timeout: float = 10) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.js(expression):
                return True
            time.sleep(0.1)
        return False

    def ready(self) -> bool:
        # defer 스크립트가 실행되기 전에 누르면 아무 일도 일어나지 않아 먼저 기다린다
        return self.wait("document.readyState==='complete'")

    def go(self, url: str) -> None:
        self.call("Page.navigate", url=url)
        time.sleep(0.2)
        self.ready()

    def resize(self, width: int, height: int, mobile: bool) -> None:
        self.call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=mobile,
        )

    def shot(self, name: str) -> None:
        data = self.call("Page.captureScreenshot", format="png")["data"]
        (self.shots_dir / name).write_bytes(base64.b64decode(data))

    def fill(self, **values: object) -> None:
        for element_id, value in values.items():
            element = f"document.getElementById({json.dumps(element_id.replace('_dash_', '-'))})"
            if isinstance(value, bool):
                self.js(f"{element}.checked={str(value).lower()}")
            else:
                self.js(f"{element}.value={json.dumps(value)}")

    def submit(self, form_id: str) -> None:
        self.js(f"document.getElementById('{form_id}').requestSubmit()")

    def click(self, element_id: str) -> None:
        self.js(f"document.getElementById('{element_id}').click()")

    def text(self, element_id: str) -> str:
        return self.js(f"document.getElementById('{element_id}').textContent") or ""

    def press(self, key: str, code: str, windows_key: int, text: str = "") -> None:
        # 사람이 누른 것과 같은 키 이벤트를 보낸다. 포커스된 버튼의 기본 동작까지 함께 확인된다
        common = {"key": key, "code": code, "windowsVirtualKeyCode": windows_key}
        self.call("Input.dispatchKeyEvent", type="keyDown", text=text, **common)
        self.call("Input.dispatchKeyEvent", type="keyUp", **common)

    def upload(self, element_id: str, path: Path) -> None:
        root = self.call("DOM.getDocument")["root"]["nodeId"]
        node = self.call("DOM.querySelector", nodeId=root, selector=f"#{element_id}")["nodeId"]
        self.call("DOM.setFileInputFiles", nodeId=node, files=[str(path)])


class Report:
    def __init__(self) -> None:
        self.results: list[bool] = []

    def check(self, name: str, passed: bool, detail: object = "") -> None:
        self.results.append(bool(passed))
        suffix = f" ({detail})" if detail != "" and not passed else ""
        print(f"{'PASS' if passed else 'FAIL'} {name}{suffix}", flush=True)


class Session:
    password = TEST_PASSWORD

    """한 번의 점검에 필요한 서버 주소, 브라우저, 결과, 메일 로그를 묶는다."""

    def __init__(self, base_url: str, browser: Browser, report: Report, log_path: Path) -> None:
        self.base = base_url
        self.browser = browser
        self.report = report
        self.log_path = log_path

    def verification_link(self, email: str) -> str:
        # 개발 환경은 메일을 콘솔에 출력하므로 서버 로그에서 받는 사람의 최근 링크를 찾는다
        log_text = self.log_path.read_bytes().decode("utf-8", "replace")
        pattern = rf"받는 사람: {re.escape(email)}.*?(http\S+/verify-email#token=[\w-]+)"
        return re.findall(pattern, log_text, flags=re.DOTALL)[-1]

    def log_without_mail_links(self) -> str:
        log_text = self.log_path.read_bytes().decode("utf-8", "replace")
        return re.sub(r"http\S+/verify-email#token=[\w-]+", "", log_text)

    def sign_up(self, email: str, display_name: str) -> None:
        browser = self.browser
        browser.go(f"{self.base}/signup")
        browser.fill(
            email=email,
            password=TEST_PASSWORD,
            display_name=display_name,
            terms_agreed=True,
            privacy_agreed=True,
        )
        browser.submit("signup-form")
        browser.wait("location.pathname==='/signup/sent'")

    def log_in(self, email: str) -> bool:
        browser = self.browser
        browser.go(f"{self.base}/login")
        browser.fill(email=email, password=TEST_PASSWORD)
        browser.submit("login-form")
        reached_home = browser.wait(
            "location.pathname==='/' && !!document.getElementById('logout-button')"
        )
        browser.ready()
        return reached_home

    def log_out(self) -> bool:
        self.browser.ready()
        self.browser.click("logout-button")
        return self.browser.wait("location.pathname==='/login'")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_url(url: str, timeout: float = 30) -> bytes:
    deadline = time.time() + timeout
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.read()
        except OSError:
            if time.time() >= deadline:
                raise
            time.sleep(0.2)


def find_browser() -> str:
    candidates = [os.environ.get("BROWSER_PATH"), *BROWSER_CANDIDATES, shutil.which("chrome"), shutil.which("msedge")]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("Chrome 또는 Edge를 찾을 수 없습니다. BROWSER_PATH 환경변수로 지정해 주세요.")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-10 - smart-voca - 시연 설정의 서버에 가상 회원 여러 명이 동시에 가입부터 시험까지 해 보는 1회성 점검
# 파일 위치: ai-agent/scripts/261110-concurrent_check.py
#
# 실행 (프로젝트 루트): .venv\Scripts\python ai-agent/scripts/261110-concurrent_check.py [회원 수, 기본 10]
# 임시 폴더에 SQLite DB를 만들고 127.0.0.1에서만 서버를 띄운다. 터널을 열지 않고 개발·시연 DB를 건드리지 않는다.
# 시연은 동기 6명 + 발표자로 예상한다 (구성안 v0.2 §10). 그보다 넉넉하게 10명을 기본으로 한다.

import os
import secrets
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CARDS_TO_MEMORIZE = 20  # 하루 새 단어 기본값
TEST_QUESTION_COUNT = 10
SLOW_SECONDS = 3.0  # 시연에서 사람이 답답하게 느낄 만한 응답 시간


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class VirtualMember:
    """회원 한 명의 흐름. 쿠키는 Secure라 http로는 저장되지 않아 직접 붙인다."""

    def __init__(self, number: int, base: str, timings: dict, problems: list) -> None:
        self.number = number
        self.client = httpx.Client(base_url=base, timeout=60)
        self.timings = timings
        self.problems = problems
        self.headers: dict[str, str] = {}

    def call(self, step: str, method: str, path: str, expected: int, **kwargs) -> httpx.Response | None:
        started = time.perf_counter()
        try:
            response = self.client.request(method, path, headers=self.headers, **kwargs)
        except httpx.HTTPError as error:
            self.problems.append(f"회원 {self.number} {step}: 연결 오류 {error!r}")
            return None
        self.timings[step].append(time.perf_counter() - started)
        if response.status_code != expected:
            self.problems.append(f"회원 {self.number} {step}: {response.status_code} {response.text[:200]}")
            return None
        return response

    def run(self, start_gate: threading.Barrier) -> None:
        email = f"member{self.number}-{secrets.token_hex(3)}@example.com"
        password = f"Practice-{secrets.token_hex(6)}"
        start_gate.wait()  # 모두 같은 순간에 시작한다
        signup = {"email": email, "password": password, "display_name": f"회원{self.number}",
                  "terms_agreed": True, "privacy_agreed": True}
        if not self.call("가입", "POST", "/api/v1/auth/signup", 202, json=signup):
            return
        login = self.call("로그인", "POST", "/api/v1/auth/login", 200, json={"email": email, "password": password})
        if not login:
            return
        self.headers["Cookie"] = f"sv_session={login.cookies.get('sv_session')}"
        session = self.call("세션 조회", "GET", "/api/v1/auth/session", 200)
        if not session:
            return
        self.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        books = self.call("단어장 목록", "GET", "/api/v1/wordbooks", 200)
        if not books:
            return
        first_book = books.json()["items"][0]["id"]
        if not self.call("단어장 담기", "POST", f"/api/v1/wordbooks/{first_book}/add", 200):
            return
        plan = self.call("일차 만들기", "POST", "/api/v1/plans", 201)
        if not plan:
            return
        for item in plan.json()["items"][:CARDS_TO_MEMORIZE]:
            if not self.call("암기 카드", "PATCH", f"/api/v1/plan-items/{item['id']}", 200, json={"done": True}):
                return
        test_request = {"test_format": "multiple", "test_direction": "en_ko", "count": TEST_QUESTION_COUNT}
        test = self.call("시험 시작", "POST", "/api/v1/tests", 201, json=test_request)
        if not test:
            return
        detail = test.json()
        answers = [{"item_id": item["id"], "answer": 0} for item in detail["items"]]
        if not self.call("시험 제출", "POST", f"/api/v1/tests/{detail['id']}/submit", 200, json={"answers": answers}):
            return
        self.call("시험 기록", "GET", "/api/v1/tests/history", 200)
        self.call("진행률", "GET", "/api/v1/progress", 200)


def prepare_server(work_dir: Path, port: int) -> tuple[subprocess.Popen, Path]:
    environment = {
        **os.environ,
        "APP_ENV": "demo",  # 시연과 같은 설정: 자동 인증, Secure 쿠키, API 문서 닫힘
        "DATABASE_URL": f"sqlite:///{(work_dir / 'concurrent.db').as_posix()}",
        "PUBLIC_BASE_URL": "https://concurrent-check.invalid",
        "AUTH_HASH_KEY": secrets.token_urlsafe(48),
    }
    for command in (
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        [sys.executable, str(PROJECT_ROOT / "ai-agent" / "scripts" / "load_wordbooks.py")],
    ):
        subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True, capture_output=True)
    log_path = work_dir / "server.log"
    log_file = log_path.open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "--factory", "web.app:create_app", "--app-dir", "src",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_ROOT, env=environment, stdout=log_file, stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                return server, log_path
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    server.terminate()
    raise RuntimeError("서버가 30초 안에 뜨지 않았습니다.")


def print_report(timings: dict, problems: list, log_path: Path, member_count: int, elapsed: float) -> bool:
    print(f"\n동시 회원 {member_count}명, 전체 {elapsed:.1f}초")
    print(f"{'단계':<10} {'횟수':>5} {'평균(초)':>9} {'최대(초)':>9}")
    for step, values in timings.items():
        print(f"{step:<10} {len(values):>5} {statistics.mean(values):>9.2f} {max(values):>9.2f}")
    slow = [step for step, values in timings.items() if max(values) > SLOW_SECONDS]
    log_text = log_path.read_text("utf-8", "replace")
    server_errors = [line for line in log_text.splitlines() if "Traceback" in line or "database is locked" in line]
    print(f"\n실패한 요청: {len(problems)}건")
    for problem in problems[:20]:
        print("  ", problem)
    print(f"서버 로그 오류: {len(server_errors)}건")
    for line in server_errors[:10]:
        print("  ", line)
    print(f"{SLOW_SECONDS}초를 넘은 단계: {', '.join(slow) if slow else '없음'}")
    return not problems and not server_errors


def remove_work_dir(work_dir: Path) -> None:
    # .venv의 python.exe는 실제 파이썬을 자식으로 띄우는 실행기라, 종료 직후 잠시 DB 파일을 잡고 있을 수 있다
    for _ in range(20):
        try:
            shutil.rmtree(work_dir)
            return
        except PermissionError:
            time.sleep(0.5)
    print(f"임시 폴더를 지우지 못했습니다: {work_dir}")


def main() -> int:
    member_count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    work_dir = Path(tempfile.mkdtemp(prefix="smart-voca-concurrent-"))
    try:
        port = free_port()
        server, log_path = prepare_server(work_dir, port)
        try:
            timings: dict[str, list[float]] = defaultdict(list)
            problems: list[str] = []
            gate = threading.Barrier(member_count)
            members = [VirtualMember(n + 1, f"http://127.0.0.1:{port}", timings, problems) for n in range(member_count)]
            threads = [threading.Thread(target=member.run, args=(gate,)) for member in members]
            started = time.perf_counter()
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            passed = print_report(timings, problems, log_path, member_count, time.perf_counter() - started)
        finally:
            server.terminate()
            server.wait(10)
    finally:
        remove_work_dir(work_dir)
    print("결과:", "통과" if passed else "문제 있음")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

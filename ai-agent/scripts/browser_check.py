#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 실제 서버와 헤드리스 브라우저로 화면 흐름을 점검한다 (테스트 정의서 §4)
# 파일 위치: ai-agent/scripts/browser_check.py
#
# 실행 (프로젝트 루트): .venv\Scripts\python ai-agent/scripts/browser_check.py
# 자동 테스트는 자바스크립트를 실행하지 않으므로, 화면 동작은 이 도구로 마일스톤마다 확인한다.
# 임시 폴더의 DB만 쓴다. data/wordbooks.json의 표본 단어장과 점검용 작은 단어장을 임시 DB에 넣는다.

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from browser_check_lib import PROJECT_ROOT, Browser, Report, Session, find_browser, free_port, wait_for_url
from browser_checks_auth import check_auth_flow
from browser_checks_learning import check_home_and_memorize
from browser_checks_settings import check_settings_flow
from browser_checks_tests import check_tests_flow
from browser_checks_words import check_words_flow, write_check_wordbooks


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
    # 공용 단어장은 운영자 도구로만 넣을 수 있으므로 서버를 띄우기 전에 같은 도구로 넣는다 (결정 D-WB05)
    check_manifest = write_check_wordbooks(work_dir / "check_wordbooks")
    for manifest_args in ([], ["--manifest", str(check_manifest)]):
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "ai-agent" / "scripts" / "load_wordbooks.py"), *manifest_args],
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
            check_words_flow(session)
            check_settings_flow(session)
            check_home_and_memorize(session)
            check_tests_flow(session)
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

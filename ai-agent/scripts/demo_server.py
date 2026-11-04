#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시연용 서버와 ngrok 터널을 함께 실행하고, 시연 DB를 지운다 (D-W19)
# 파일 위치: ai-agent/scripts/demo_server.py
#
# 실행 (프로젝트 루트): .venv\Scripts\python ai-agent/scripts/demo_server.py start
# 시연 DB 삭제:         .venv\Scripts\python ai-agent/scripts/demo_server.py reset
# Ctrl+C로 끝내면 서버와 터널이 함께 닫힌다. 시연 때만 열고 바로 닫는다.

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# 개발 DB와 섞이지 않게 시연 전용 파일을 쓴다. 지우는 대상도 이 파일뿐이다
DEMO_DB_PATH = PROJECT_ROOT / "data" / "smart_voca_demo.db"
DEMO_DATABASE_URL = "sqlite:///data/smart_voca_demo.db"
APP_PORT = 8000
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
TUNNEL_WAIT_SECONDS = 20


def find_public_url() -> str | None:
    try:
        with urllib.request.urlopen(NGROK_API_URL, timeout=2) as response:
            tunnels = json.load(response)["tunnels"]
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        return None
    for tunnel in tunnels:
        if tunnel.get("public_url", "").startswith("https://"):
            return tunnel["public_url"]
    return None


def wait_for_public_url(tunnel: subprocess.Popen) -> str | None:
    deadline = time.time() + TUNNEL_WAIT_SECONDS
    while time.time() < deadline and tunnel.poll() is None:
        public_url = find_public_url()
        if public_url:
            return public_url
        time.sleep(0.5)
    return None


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(10)
    except subprocess.TimeoutExpired:
        process.kill()


def start() -> int:
    ngrok = shutil.which("ngrok")
    if ngrok is None:
        print("ngrok을 찾을 수 없습니다. 설치한 뒤 다시 실행해 주세요.")
        return 1
    if find_public_url():
        print("이미 열린 ngrok 터널이 있습니다. 먼저 닫아 주세요.")
        return 1

    tunnel = server = None
    with tempfile.TemporaryDirectory(prefix="smart-voca-demo-") as temp_dir:
        tunnel_log = Path(temp_dir) / "ngrok.log"
        try:
            # 주소가 있어야 서버 설정을 만들 수 있어 터널을 먼저 연다
            tunnel = subprocess.Popen(
                [ngrok, "http", str(APP_PORT), "--log", str(tunnel_log), "--log-format", "logfmt"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            public_url = wait_for_public_url(tunnel)
            if public_url is None:
                print("ngrok 터널을 열지 못했습니다. 로그 끝부분:")
                if tunnel_log.exists():
                    print("\n".join(tunnel_log.read_text("utf-8", "replace").splitlines()[-5:]))
                return 1

            environment = {
                **os.environ,
                "APP_ENV": "demo",
                "DATABASE_URL": DEMO_DATABASE_URL,
                "PUBLIC_BASE_URL": public_url,
                # 실행할 때마다 새로 만들어 비밀값을 파일에 남기지 않는다
                "AUTH_HASH_KEY": secrets.token_urlsafe(48),
            }
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=PROJECT_ROOT,
                env=environment,
                check=True,
                capture_output=True,
            )
            server = subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn", "--factory", "web.app:create_app",
                    "--app-dir", "src", "--host", "127.0.0.1", "--port", str(APP_PORT),
                    # 터널은 이 PC에서 접속한다. 이 주소가 보낸 헤더만 믿어 참가자별 IP를 얻는다 (NFR-DEMO-04)
                    "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1",
                ],
                cwd=PROJECT_ROOT,
                env=environment,
            )
            print(f"\n시연 주소: {public_url}")
            print("경고 페이지가 나오면 Visit을 누르도록 안내해 주세요. 끝내려면 Ctrl+C를 누르세요.\n", flush=True)
            while server.poll() is None and tunnel.poll() is None:
                time.sleep(1)
            print("서버 또는 터널이 종료되었습니다.")
            return 1
        except KeyboardInterrupt:
            print("\n시연을 끝냅니다. 시연 DB를 지우려면 reset을 실행하세요.")
            return 0
        except subprocess.CalledProcessError as error:
            print(f"DB를 준비하지 못했습니다: {error.stderr.decode('utf-8', 'replace')[-500:]}")
            return 1
        finally:
            stop(server)
            stop(tunnel)


def reset() -> int:
    if find_public_url():
        print("터널이 열려 있습니다. 시연을 끝낸 뒤 실행해 주세요.")
        return 1
    if not DEMO_DB_PATH.exists():
        print("지울 시연 DB가 없습니다.")
        return 0
    DEMO_DB_PATH.unlink()
    print(f"시연 DB를 지웠습니다: {DEMO_DB_PATH.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="smart-voca 시연 서버")
    parser.add_argument("command", choices=("start", "reset"))
    return start() if parser.parse_args().command == "start" else reset()


if __name__ == "__main__":
    sys.exit(main())

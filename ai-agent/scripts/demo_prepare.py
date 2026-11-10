#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-10 - smart-voca - 열린 시연 주소에 발표자 시연 계정을 만들고 초급 단어장 담기와 첫 일차까지 준비한다
# 파일 위치: ai-agent/scripts/demo_prepare.py
#
# 실행 (프로젝트 루트, demo_server.py start를 띄운 뒤): .venv\Scripts\python ai-agent/scripts/demo_prepare.py 시연주소
#   --email로 이메일을 바꿀 수 있다 (기본 presenter@smart-voca.test). 비밀번호는 새로 만들어 화면에만 보여 준다.
# 발표 준비 체크리스트 당일 7번(시연 계정 만들기 → 초급 단어장 담기 → 첫 일차 만들기)을 대신한다.
# 다시 실행할 때는 앞에서 받은 비밀번호를 --password로 넘긴다. 이미 담은 단어장은 그대로 두고, 일차가 있으면 새로 만들지 않는다.

import argparse
import secrets
import sys

import httpx

DEFAULT_EMAIL = "presenter@smart-voca.test"
WORDBOOK_TITLE = "초급 단어"
# ngrok 무료 주소는 브라우저가 아닌 요청에도 경고 페이지를 낼 수 있어 이 헤더로 건너뛴다
NGROK_SKIP_HEADER = {"ngrok-skip-browser-warning": "1"}


class PrepareError(Exception):
    pass


def expect(response: httpx.Response, status: int, step: str) -> httpx.Response:
    if response.status_code != status:
        raise PrepareError(f"{step} 실패: {response.status_code} {response.text[:200]}")
    return response


def prepare(base: str, email: str, password: str, password_given: bool) -> dict:
    with httpx.Client(base_url=base, headers=NGROK_SKIP_HEADER, timeout=30) as client:
        expect(client.get("/healthz"), 200, "서버 확인")
        credentials = {"email": email, "password": password}
        # 다시 실행할 때 가입을 또 보내면 같은 이메일 1분 제한(429)에 걸려서 로그인을 먼저 해 본다
        login = client.post("/api/v1/auth/login", json=credentials)
        if login.status_code == 401 and not password_given:
            signup = {**credentials, "display_name": "발표자", "terms_agreed": True, "privacy_agreed": True}
            # 이미 있는 이메일도 같은 202로 답한다(가입 여부를 알려 주지 않는다). 그래서 다시 로그인으로 확인한다
            signed_up = client.post("/api/v1/auth/signup", json=signup)
            if signed_up.status_code == 429:
                raise PrepareError(
                    "가입 요청이 너무 잦습니다. 이 이메일로 방금 만든 계정이 있다면 그 비밀번호를 --password로 넘기고, "
                    "아니면 1분 뒤 다시 실행하세요."
                )
            expect(signed_up, 202, "가입")
            login = client.post("/api/v1/auth/login", json=credentials)
        if login.status_code == 401:
            raise PrepareError(
                "로그인 실패: 이 이메일로 이미 계정이 있습니다. 앞에서 받은 비밀번호를 --password로 넘기거나, "
                "--email로 다른 이메일을 쓰세요."
            )
        expect(login, 200, "로그인")
        # 쿠키는 Secure라 https 주소에서만 저장된다. 이 PC 안의 http 주소로 시험할 때도 동작하게 직접 붙인다
        client.headers["Cookie"] = f"sv_session={login.cookies.get('sv_session')}"
        csrf_token = expect(client.get("/api/v1/auth/session"), 200, "세션 조회").json()["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf_token

        books = expect(client.get("/api/v1/wordbooks"), 200, "단어장 목록").json()["items"]
        book = next((item for item in books if item["title"] == WORDBOOK_TITLE), None)
        if book is None:
            raise PrepareError(f"'{WORDBOOK_TITLE}' 단어장이 없습니다. 서버를 demo_server.py start로 띄웠는지 확인하세요.")
        added = expect(client.post(f"/api/v1/wordbooks/{book['id']}/add"), 200, "단어장 담기").json()

        plans = expect(client.get("/api/v1/plans"), 200, "일차 목록").json()
        if plans["current_day"] >= 1:
            day = plans["current_day"]
            item_count = next((summary["total"] for summary in plans["items"] if summary["day"] == day), 0)
            created = False
        else:
            plan = expect(client.post("/api/v1/plans"), 201, "일차 만들기").json()
            day, item_count, created = plan["day"], len(plan["items"]), True
        expect(client.post("/api/v1/auth/logout"), 204, "로그아웃")
    return {"added": added["added"], "already_had": added["already_had"],
            "day": day, "item_count": item_count, "created": created}


def main() -> int:
    parser = argparse.ArgumentParser(description="smart-voca 시연 계정 준비")
    parser.add_argument("url", help="demo_server.py start가 보여 준 시연 주소")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", help="다시 실행할 때 앞에서 받은 비밀번호")
    args = parser.parse_args()
    # 실제로 쓰는 비밀번호를 넣지 않도록 처음에는 새로 만든다. 파일에 남기지 않는다
    password = args.password or f"Demo-{secrets.token_hex(4)}"
    try:
        result = prepare(args.url.rstrip("/"), args.email, password, args.password is not None)
    except (PrepareError, httpx.HTTPError) as error:
        print(error)
        return 1
    print("시연 계정을 준비했습니다.")
    print(f"  이메일:   {args.email}")
    print(f"  비밀번호: {password}   (이 창에만 보입니다. 브라우저 로그인에 쓰세요)")
    print(f"  {WORDBOOK_TITLE}: {result['added']}개 담음, 이미 있던 단어 {result['already_had']}개")
    state = "새로 만듦" if result["created"] else "이미 있음"
    print(f"  {result['day']}일차: 단어 {result['item_count']}개 ({state})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

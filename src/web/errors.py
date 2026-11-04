#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - API 오류를 설계에서 정한 형식으로 응답한다 (API 설계 §1.3)
# 파일 위치: src/web/errors.py

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

API_PREFIX = "/api/"
HTTP_ERROR_CODES = {
    404: ("NOT_FOUND", "찾을 수 없습니다."),
    405: ("METHOD_NOT_ALLOWED", "허용되지 않는 요청입니다."),
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.retry_after = retry_after


def error_response(error: ApiError) -> JSONResponse:
    body: dict[str, object] = {"code": error.code, "message": error.message}
    headers = {}
    if error.fields:
        body["fields"] = error.fields
    if error.retry_after is not None:
        body["retry_after"] = error.retry_after
        headers["Retry-After"] = str(error.retry_after)
    return JSONResponse({"error": body}, status_code=error.status_code, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # FastAPI 기본 응답은 입력값을 되돌려줘 비밀번호가 응답에 담기므로 칸 이름만 알려 준다
        fields = {}
        for detail in error.errors():
            location = detail.get("loc", ())
            if len(location) >= 2 and isinstance(location[-1], str):
                fields[location[-1]] = "입력값을 확인해 주세요."
        return error_response(
            ApiError(400, "VALIDATION_FAILED", "입력값을 확인해 주세요.", fields=fields)
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException):
        # 화면 주소는 기본 동작을 유지하고 API 주소만 설계 형식으로 바꾼다
        if not request.url.path.startswith(API_PREFIX):
            return await http_exception_handler(request, error)
        code, message = HTTP_ERROR_CODES.get(
            error.status_code, ("REQUEST_FAILED", "요청을 처리할 수 없습니다.")
        )
        return error_response(ApiError(error.status_code, code, message))

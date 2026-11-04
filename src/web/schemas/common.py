#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 여러 API가 함께 쓰는 입력 형식
# 파일 위치: src/web/schemas/common.py

from typing import Annotated

from pydantic import Field

# PostgreSQL INTEGER의 최댓값. 넘는 값은 DB 드라이버에서 예외가 나므로 입력에서 막는다
MAX_DB_INT = 2_147_483_647

DbInt = Annotated[int, Field(ge=1, le=MAX_DB_INT)]

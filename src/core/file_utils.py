#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-28 - smart-voca - 안전한 파일 저장(임시 파일 후 교체)과 백업 (file_utils)
# 파일 위치: src/core/file_utils.py
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional, TextIO


@contextmanager
def atomic_write(path: Path, encoding: str) -> Iterator[TextIO]:
    """파일을 안전하게 쓴다.
    임시 파일에 먼저 쓰고, 끝까지 성공했을 때만 원래 파일을 교체한다.
    쓰는 도중 오류가 나도 원래 파일은 그대로 남는다 (설계 D-22).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    try:
        with open(temp_path, "w", encoding=encoding, newline="") as temp_file:
            yield temp_file
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def backup_file(source: Path, backup_dir: Path) -> Optional[Path]:
    """원본 파일을 백업 폴더에 날짜·시각을 붙여 복사한다. 원본이 없으면 None을 돌려준다."""
    if not source.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    # 마이크로초까지 붙여서 같은 초에 두 번 백업해도 이름이 겹치지 않게 한다
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"{source.stem}_{stamp}{source.suffix}"
    target.write_bytes(source.read_bytes())
    return target


def prune_backups(backup_dir: Path, file_prefix: str, keep_count: int) -> List[Path]:
    """백업 폴더에서 file_prefix로 시작하는 파일 중 오래된 것부터 지워 keep_count개만 남긴다.
    이름에 붙은 시각 순서로 판단한다. 다른 이름의 파일은 건드리지 않는다. 지운 파일 목록을 돌려준다 (설계 D-25).
    """
    if not backup_dir.exists():
        return []
    backups = sorted(path for path in backup_dir.glob(f"{file_prefix}*") if path.is_file())
    excess = backups[:max(len(backups) - keep_count, 0)]
    for path in excess:
        path.unlink()
    return excess

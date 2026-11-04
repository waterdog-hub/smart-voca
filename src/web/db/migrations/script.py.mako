#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ${create_date.strftime("%Y-%m-%d")} - smart-voca - 마이그레이션: ${message}
# 파일 위치: src/web/db/migrations/versions/

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}

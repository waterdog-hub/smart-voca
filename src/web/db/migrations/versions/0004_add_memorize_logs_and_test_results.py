#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-25 - smart-voca - 마이그레이션: 암기 이력(memorize_logs)과 문항별 시험 결과(test_results) (VOCA-FR-014, 026)
# 파일 위치: src/web/db/migrations/versions/

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('memorize_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('word_id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("action IN ('done', 'later')", name=op.f('ck_memorize_logs_action_allowed')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_memorize_logs_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['word_id'], ['words.id'], name=op.f('fk_memorize_logs_word_id_words')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_memorize_logs'))
    )
    with op.batch_alter_table('memorize_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_memorize_logs_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_memorize_logs_word_id'), ['word_id'], unique=False)

    op.create_table('test_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('word_id', sa.Integer(), nullable=False),
    sa.Column('test_format', sa.String(length=20), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('answered', sa.Boolean(), nullable=False),
    sa.Column('answered_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['test_sessions.id'], name=op.f('fk_test_results_session_id_test_sessions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_test_results_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['word_id'], ['words.id'], name=op.f('fk_test_results_word_id_words')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_test_results'))
    )
    with op.batch_alter_table('test_results', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_test_results_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_test_results_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_test_results_word_id'), ['word_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('test_results', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_test_results_word_id'))
        batch_op.drop_index(batch_op.f('ix_test_results_user_id'))
        batch_op.drop_index(batch_op.f('ix_test_results_session_id'))
    op.drop_table('test_results')
    with op.batch_alter_table('memorize_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_memorize_logs_word_id'))
        batch_op.drop_index(batch_op.f('ix_memorize_logs_user_id'))
    op.drop_table('memorize_logs')

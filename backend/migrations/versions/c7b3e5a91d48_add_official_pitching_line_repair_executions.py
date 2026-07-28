"""add the governed official pitching-line repair execution ledger

Foundation 3A. Adds the durable execution record for the ONE reviewed, fingerprint-locked
official pitching-line repair. Purely additive: a single new table, no existing table
touched, no existing row modified, no backfill.

Two invariants are enforced at the database rather than by writer discipline. ``status``
may only ever be ``completed`` — a repair that did not commit performs no writes and so has
nothing to record — and ``approved_manifest_fingerprint`` is UNIQUE, so a second completed
execution of the same approved manifest is impossible even under concurrent dispatch. The
action counts must also sum to the recorded total, so a miscounted row cannot be stored.

One Alembic head is preserved; downgrade drops only this table and is independently
reversible.

Revision ID: c7b3e5a91d48
Revises: a4f1c7e9b3d2
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'c7b3e5a91d48'
down_revision = 'a4f1c7e9b3d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'official_pitching_line_repair_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('capability', sa.String(length=120), nullable=False),
        sa.Column('approved_manifest_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('regenerated_manifest_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('planner_git_sha', sa.String(length=64), nullable=True),
        sa.Column('apply_git_sha', sa.String(length=64), nullable=True),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('accepted_baseline_version', sa.String(length=16), nullable=False),
        sa.Column('amendment_id', sa.String(length=120), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('identity_action_count', sa.Integer(), nullable=False),
        sa.Column('insert_action_count', sa.Integer(), nullable=False),
        sa.Column('update_action_count', sa.Integer(), nullable=False),
        sa.Column('total_action_count', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('committed_at', sa.DateTime(), nullable=True),
        sa.Column('execution_summary', sa.JSON(), nullable=True),
        sa.Column('precondition_summary', sa.JSON(), nullable=True),
        sa.Column('verification_summary', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'approved_manifest_fingerprint',
            name='uq_oplr_executions_approved_fingerprint',
        ),
        sa.CheckConstraint(
            "status = 'completed'",
            name='ck_oplr_executions_status_completed',
        ),
        sa.CheckConstraint(
            'identity_action_count >= 0 AND insert_action_count >= 0 '
            'AND update_action_count >= 0 AND total_action_count = '
            '(identity_action_count + insert_action_count + update_action_count)',
            name='ck_oplr_executions_action_counts_reconcile',
        ),
    )
    with op.batch_alter_table(
        'official_pitching_line_repair_executions', schema=None,
    ) as batch_op:
        batch_op.create_index(
            'ix_oplr_executions_capability', ['capability'], unique=False,
        )
        batch_op.create_index(
            'ix_oplr_executions_committed_at', ['committed_at'], unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        'official_pitching_line_repair_executions', schema=None,
    ) as batch_op:
        batch_op.drop_index('ix_oplr_executions_committed_at')
        batch_op.drop_index('ix_oplr_executions_capability')
    op.drop_table('official_pitching_line_repair_executions')

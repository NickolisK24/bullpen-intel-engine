"""add the durable game-level ingestion work-state checkpoint

Foundation 3C. The daily publication-critical appearance lane's unit of work
becomes ONE GAME instead of one pitcher, and this table is that lane's durable
checkpoint: which governed games have been planned, attempted, and fully
reconciled, at which observed source revision.

Purely additive and production-safe:

  * one new table, no existing table altered;
  * no existing row modified, no game_log rewritten, no backfill;
  * no historical game is marked complete — completion is only ever written by
    a run that proved it, so deployment cannot fabricate completeness.

Rollout seeding is deliberately NOT done in this migration. An empty table
means "no game has been proven complete by this lane yet", which fails closed:
the completeness proof reports unresolved final games until the lane has
actually run. That is the correct initial state.

Three invariants are enforced at the database rather than by writer discipline:
the status / criticality / candidate-reason vocabularies are closed sets, and a
row may only be ``completed`` when it carries a completion timestamp, a
determined row expectation, and an exact reconciliation of that expectation.

One Alembic head is preserved; downgrade drops only this table.

Revision ID: b9d4e17c3a80
Revises: c7b3e5a91d48
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = 'b9d4e17c3a80'
down_revision = 'c7b3e5a91d48'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'game_ingestion_work_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
        sa.Column('represented_date', sa.Date(), nullable=False),
        sa.Column('game_date', sa.Date(), nullable=True),
        sa.Column('game_type', sa.String(length=2), nullable=True),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('game_datetime', sa.DateTime(), nullable=True),
        sa.Column('candidate_reason', sa.String(length=40), nullable=False),
        sa.Column('criticality', sa.String(length=30), nullable=False),
        sa.Column('finality_state', sa.String(length=30), nullable=True),
        sa.Column('source_authority', sa.String(length=60), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('first_attempted_at', sa.DateTime(), nullable=True),
        sa.Column('last_attempted_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_class', sa.String(length=60), nullable=True),
        sa.Column('source_revision', sa.String(length=64), nullable=True),
        sa.Column('rows_expected', sa.Integer(), nullable=True),
        sa.Column('rows_reconciled', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('relief_rows_reconciled', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('correction_count', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('completion_proof', sa.JSON(), nullable=True),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'mlb_game_pk', name='uq_game_ingestion_work_items_game_pk',
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'in_progress', 'completed', "
            "'retryable_failure', 'terminal_failure', 'superseded')",
            name='ck_game_ingestion_work_items_status',
        ),
        sa.CheckConstraint(
            "criticality IN ('publication_critical', 'best_effort', 'unknown')",
            name='ck_game_ingestion_work_items_criticality',
        ),
        sa.CheckConstraint(
            "candidate_reason IN ('newly_final', 'finality_changed', "
            "'corrected_final', 'incomplete_prior_attempt', 'explicit_repair', "
            "'backfill')",
            name='ck_game_ingestion_work_items_candidate_reason',
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR ("
            "completed_at IS NOT NULL AND rows_expected IS NOT NULL "
            "AND rows_reconciled = rows_expected AND rows_expected > 0)",
            name='ck_game_ingestion_work_items_completion_proof',
        ),
        sa.CheckConstraint(
            'attempt_count >= 0 AND rows_reconciled >= 0 '
            'AND (rows_expected IS NULL OR rows_expected >= 0)',
            name='ck_game_ingestion_work_items_counts_nonnegative',
        ),
    )
    with op.batch_alter_table('game_ingestion_work_items', schema=None) as batch_op:
        batch_op.create_index(
            'ix_game_ingestion_work_items_status_date',
            ['status', 'represented_date'],
            unique=False,
        )
        batch_op.create_index(
            'ix_game_ingestion_work_items_represented_date',
            ['represented_date'],
            unique=False,
        )
        batch_op.create_index(
            'ix_game_ingestion_work_items_criticality_status',
            ['criticality', 'status'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('game_ingestion_work_items', schema=None) as batch_op:
        batch_op.drop_index('ix_game_ingestion_work_items_criticality_status')
        batch_op.drop_index('ix_game_ingestion_work_items_represented_date')
        batch_op.drop_index('ix_game_ingestion_work_items_status_date')
    op.drop_table('game_ingestion_work_items')

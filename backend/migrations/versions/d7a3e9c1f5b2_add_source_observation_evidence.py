"""add immutable source observations, artifacts, and fetch attempts

Revision ID: d7a3e9c1f5b2
Revises: c4f8a2d7e6b1
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = 'd7a3e9c1f5b2'
down_revision = 'c4f8a2d7e6b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'source_subjects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('identity_key', sa.String(length=64), nullable=False),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('source_domain', sa.String(length=40), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('subject_type', sa.String(length=40), nullable=False),
        sa.Column('subject_key', sa.String(length=255), nullable=False),
        sa.Column('request_identity', sa.String(length=64), nullable=False),
        sa.Column('request_schema_version', sa.Integer(), nullable=False),
        sa.Column('request_parameters', sa.JSON(), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=True),
        sa.Column('range_start', sa.Date(), nullable=True),
        sa.Column('range_end', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('identity_key', name='uq_source_subjects_identity_key'),
    )
    op.create_index(
        'ix_source_subjects_provider_domain',
        'source_subjects',
        ['provider', 'source_domain', 'id'],
    )
    op.create_index(
        'ix_source_subjects_subject',
        'source_subjects',
        ['subject_type', 'subject_key', 'id'],
    )
    op.create_index(
        'ix_source_subjects_baseball_date',
        'source_subjects',
        ['baseball_date', 'id'],
    )
    op.create_index(
        'ix_source_subjects_request_identity',
        'source_subjects',
        ['request_identity'],
    )

    op.create_table(
        'source_payload_artifacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('hash_algorithm', sa.String(length=20), nullable=False),
        sa.Column('payload_schema_version', sa.Integer(), nullable=False),
        sa.Column('payload_kind', sa.String(length=30), nullable=False),
        sa.Column('storage_format', sa.String(length=20), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('payload_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'content_hash',
            'payload_schema_version',
            'payload_kind',
            name='uq_source_payload_artifacts_content_schema_kind',
        ),
    )
    op.create_index(
        'ix_source_payload_artifacts_content_hash',
        'source_payload_artifacts',
        ['content_hash'],
    )

    op.create_table(
        'source_observations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_subject_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('dedupe_key', sa.String(length=64), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('fingerprint_algorithm', sa.String(length=20), nullable=False),
        sa.Column('fingerprint_version', sa.String(length=40), nullable=False),
        sa.Column('payload_schema_version', sa.Integer(), nullable=False),
        sa.Column('payload_artifact_id', sa.Integer(), nullable=True),
        sa.Column('completeness', sa.String(length=20), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('is_change', sa.Boolean(), nullable=False),
        sa.Column('is_authoritative', sa.Boolean(), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=True),
        sa.Column('source_updated_at', sa.DateTime(), nullable=True),
        sa.Column('source_revision', sa.String(length=160), nullable=True),
        sa.Column('source_etag', sa.String(length=255), nullable=True),
        sa.Column('predecessor_observation_id', sa.Integer(), nullable=True),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('sync_job_id', sa.Integer(), nullable=True),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "completeness IN ('complete', 'partial', 'unknown')",
            name='ck_source_observations_completeness',
        ),
        sa.CheckConstraint(
            "outcome IN ('new', 'changed', 'corrected', 'partial', 'empty_valid')",
            name='ck_source_observations_outcome',
        ),
        sa.CheckConstraint(
            'version_number > 0 AND payload_schema_version > 0',
            name='ck_source_observations_version_bounds',
        ),
        sa.CheckConstraint(
            'record_count IS NULL OR record_count >= 0',
            name='ck_source_observations_record_count',
        ),
        sa.ForeignKeyConstraint(
            ['source_subject_id'], ['source_subjects.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['payload_artifact_id'], ['source_payload_artifacts.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['predecessor_observation_id'], ['source_observations.id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.ForeignKeyConstraint(['sync_job_id'], ['sync_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_subject_id',
            'version_number',
            name='uq_source_observations_subject_version',
        ),
        sa.UniqueConstraint('dedupe_key', name='uq_source_observations_dedupe_key'),
    )
    op.create_index(
        'ix_source_observations_subject_latest',
        'source_observations',
        ['source_subject_id', 'version_number'],
    )
    op.create_index(
        'ix_source_observations_subject_authoritative',
        'source_observations',
        ['source_subject_id', 'is_authoritative', 'version_number'],
    )
    op.create_index(
        'ix_source_observations_fingerprint',
        'source_observations',
        ['fingerprint'],
    )
    op.create_index(
        'ix_source_observations_outcome_created',
        'source_observations',
        ['outcome', 'created_at'],
    )
    op.create_index(
        'ix_source_observations_predecessor',
        'source_observations',
        ['predecessor_observation_id'],
    )
    op.create_index(
        'ix_source_observations_sync_run',
        'source_observations',
        ['sync_run_id', 'id'],
    )
    op.create_index(
        'ix_source_observations_sync_job',
        'source_observations',
        ['sync_job_id', 'id'],
    )

    op.create_table(
        'source_fetch_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_subject_id', sa.Integer(), nullable=False),
        sa.Column('source_observation_id', sa.Integer(), nullable=True),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('sync_job_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('completeness', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=False),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('http_retry_count', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('response_bytes', sa.Integer(), nullable=True),
        sa.Column('record_count', sa.Integer(), nullable=True),
        sa.Column('error_class', sa.String(length=80), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'partial', 'failed')",
            name='ck_source_fetch_attempts_status',
        ),
        sa.CheckConstraint(
            "completeness IN ('complete', 'partial', 'unknown', 'failed')",
            name='ck_source_fetch_attempts_completeness',
        ),
        sa.CheckConstraint(
            "outcome IN ('new', 'unchanged', 'changed', 'corrected', "
            "'partial', 'empty_valid', 'failed')",
            name='ck_source_fetch_attempts_outcome',
        ),
        sa.CheckConstraint(
            'http_retry_count >= 0 AND '
            '(duration_ms IS NULL OR duration_ms >= 0) AND '
            '(response_bytes IS NULL OR response_bytes >= 0) AND '
            '(record_count IS NULL OR record_count >= 0)',
            name='ck_source_fetch_attempts_count_bounds',
        ),
        sa.ForeignKeyConstraint(
            ['source_subject_id'], ['source_subjects.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['source_observation_id'], ['source_observations.id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.ForeignKeyConstraint(['sync_job_id'], ['sync_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_source_fetch_attempts_subject_started',
        'source_fetch_attempts',
        ['source_subject_id', 'started_at'],
    )
    op.create_index(
        'ix_source_fetch_attempts_status_started',
        'source_fetch_attempts',
        ['status', 'started_at'],
    )
    op.create_index(
        'ix_source_fetch_attempts_observation',
        'source_fetch_attempts',
        ['source_observation_id'],
    )
    op.create_index(
        'ix_source_fetch_attempts_sync_run',
        'source_fetch_attempts',
        ['sync_run_id', 'id'],
    )
    op.create_index(
        'ix_source_fetch_attempts_sync_job',
        'source_fetch_attempts',
        ['sync_job_id', 'id'],
    )

    _add_observation_link(
        'game_observation_states',
        'fk_game_observation_states_source_observation',
        'ix_game_observation_states_source_observation',
    )
    _add_observation_link(
        'scheduled_games',
        'fk_scheduled_games_source_observation',
        'ix_scheduled_games_source_observation',
    )
    _add_observation_link(
        'player_transaction_sync_windows',
        'fk_player_transaction_sync_windows_source_observation',
        'ix_player_transaction_sync_windows_source_observation',
    )


def downgrade():
    _drop_observation_link(
        'player_transaction_sync_windows',
        'fk_player_transaction_sync_windows_source_observation',
        'ix_player_transaction_sync_windows_source_observation',
    )
    _drop_observation_link(
        'scheduled_games',
        'fk_scheduled_games_source_observation',
        'ix_scheduled_games_source_observation',
    )
    _drop_observation_link(
        'game_observation_states',
        'fk_game_observation_states_source_observation',
        'ix_game_observation_states_source_observation',
    )

    for name in (
        'ix_source_fetch_attempts_sync_job',
        'ix_source_fetch_attempts_sync_run',
        'ix_source_fetch_attempts_observation',
        'ix_source_fetch_attempts_status_started',
        'ix_source_fetch_attempts_subject_started',
    ):
        op.drop_index(name, table_name='source_fetch_attempts')
    op.drop_table('source_fetch_attempts')

    for name in (
        'ix_source_observations_sync_job',
        'ix_source_observations_sync_run',
        'ix_source_observations_predecessor',
        'ix_source_observations_outcome_created',
        'ix_source_observations_fingerprint',
        'ix_source_observations_subject_authoritative',
        'ix_source_observations_subject_latest',
    ):
        op.drop_index(name, table_name='source_observations')
    op.drop_table('source_observations')

    op.drop_index(
        'ix_source_payload_artifacts_content_hash',
        table_name='source_payload_artifacts',
    )
    op.drop_table('source_payload_artifacts')

    for name in (
        'ix_source_subjects_request_identity',
        'ix_source_subjects_baseball_date',
        'ix_source_subjects_subject',
        'ix_source_subjects_provider_domain',
    ):
        op.drop_index(name, table_name='source_subjects')
    op.drop_table('source_subjects')


def _add_observation_link(table_name, foreign_key_name, index_name):
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('source_observation_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            foreign_key_name,
            'source_observations',
            ['source_observation_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(index_name, ['source_observation_id'])


def _drop_observation_link(table_name, foreign_key_name, index_name):
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.drop_index(index_name)
        batch_op.drop_constraint(foreign_key_name, type_='foreignkey')
        batch_op.drop_column('source_observation_id')

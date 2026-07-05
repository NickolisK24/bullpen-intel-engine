"""add phase0e composed reads

Revision ID: a9d4e7c2f6b1
Revises: c8d2f4a1b6e9
Create Date: 2026-07-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a9d4e7c2f6b1'
down_revision = 'c8d2f4a1b6e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'composed_reads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('read_key', sa.String(length=220), nullable=False),
        sa.Column('read_type', sa.String(length=120), nullable=False),
        sa.Column('read_version', sa.Integer(), nullable=False),
        sa.Column('subject_type', sa.String(length=40), nullable=False),
        sa.Column('subject_id', sa.String(length=80), nullable=True),
        sa.Column('subject_key', sa.String(length=160), nullable=False),
        sa.Column('product_date', sa.Date(), nullable=False),
        sa.Column('completeness_state', sa.String(length=20), nullable=False),
        sa.Column('reason_codes', sa.JSON(), nullable=True),
        sa.Column('limitations', sa.JSON(), nullable=True),
        sa.Column('component_summary', sa.JSON(), nullable=False),
        sa.Column('posture', sa.String(length=30), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('recompute_status', sa.String(length=30), nullable=False),
        sa.Column('recompute_reason_codes', sa.JSON(), nullable=True),
        sa.Column('invalidated_at', sa.DateTime(), nullable=True),
        sa.Column('invalidated_by_source_table', sa.String(length=80), nullable=True),
        sa.Column('invalidated_by_source_pk', sa.String(length=120), nullable=True),
        sa.Column('superseded_by_read_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('pitcher_day', 'team_day')",
            name='ck_composed_reads_subject_type',
        ),
        sa.CheckConstraint(
            "completeness_state IN ('complete', 'partial', 'unknown', 'conflict', 'withheld')",
            name='ck_composed_reads_completeness_state',
        ),
        sa.CheckConstraint(
            "posture IN ('internal_only')",
            name='ck_composed_reads_posture',
        ),
        sa.CheckConstraint(
            "recompute_status IN ('current', 'recompute_needed', 'recomputed', 'superseded')",
            name='ck_composed_reads_recompute_status',
        ),
        sa.ForeignKeyConstraint(['superseded_by_read_id'], ['composed_reads.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('read_key', name='uq_composed_reads_read_key'),
    )
    op.create_index(
        'ix_composed_reads_posture',
        'composed_reads',
        ['posture'],
        unique=False,
    )
    op.create_index(
        'ix_composed_reads_recompute_status',
        'composed_reads',
        ['recompute_status'],
        unique=False,
    )
    op.create_index(
        'ix_composed_reads_subject_date',
        'composed_reads',
        ['subject_type', 'subject_key', 'product_date'],
        unique=False,
    )
    op.create_index(
        'ix_composed_reads_type_version',
        'composed_reads',
        ['read_type', 'read_version'],
        unique=False,
    )

    op.create_table(
        'composed_read_components',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('composed_read_id', sa.Integer(), nullable=False),
        sa.Column('component_name', sa.String(length=120), nullable=False),
        sa.Column('required', sa.Boolean(), nullable=False),
        sa.Column('component_state', sa.String(length=20), nullable=False),
        sa.Column('reason_codes', sa.JSON(), nullable=True),
        sa.Column('limitations', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "component_state IN ('complete', 'partial', 'unknown', 'conflict', 'withheld', 'absent')",
            name='ck_composed_read_components_state',
        ),
        sa.ForeignKeyConstraint(['composed_read_id'], ['composed_reads.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_composed_read_components_name',
        'composed_read_components',
        ['component_name'],
        unique=False,
    )
    op.create_index(
        'ix_composed_read_components_read',
        'composed_read_components',
        ['composed_read_id'],
        unique=False,
    )

    op.create_table(
        'composed_read_evidence_citations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('composed_read_component_id', sa.Integer(), nullable=False),
        sa.Column('evidence_object_id', sa.Integer(), nullable=False),
        sa.Column('citation_role', sa.String(length=60), nullable=False),
        sa.Column('cited_completeness_state', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['composed_read_component_id'],
            ['composed_read_components.id'],
        ),
        sa.ForeignKeyConstraint(['evidence_object_id'], ['evidence_objects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_composed_read_evidence_citations_component',
        'composed_read_evidence_citations',
        ['composed_read_component_id'],
        unique=False,
    )
    op.create_index(
        'ix_composed_read_evidence_citations_evidence',
        'composed_read_evidence_citations',
        ['evidence_object_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_composed_read_evidence_citations_evidence',
        table_name='composed_read_evidence_citations',
    )
    op.drop_index(
        'ix_composed_read_evidence_citations_component',
        table_name='composed_read_evidence_citations',
    )
    op.drop_table('composed_read_evidence_citations')
    op.drop_index('ix_composed_read_components_read', table_name='composed_read_components')
    op.drop_index('ix_composed_read_components_name', table_name='composed_read_components')
    op.drop_table('composed_read_components')
    op.drop_index('ix_composed_reads_type_version', table_name='composed_reads')
    op.drop_index('ix_composed_reads_subject_date', table_name='composed_reads')
    op.drop_index('ix_composed_reads_recompute_status', table_name='composed_reads')
    op.drop_index('ix_composed_reads_posture', table_name='composed_reads')
    op.drop_table('composed_reads')

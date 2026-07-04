"""add phase0d evidence contract

Revision ID: c8d2f4a1b6e9
Revises: b6e1a2f4c9d7
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c8d2f4a1b6e9'
down_revision = 'b6e1a2f4c9d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'evidence_objects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('evidence_key', sa.String(length=220), nullable=False),
        sa.Column('evidence_type', sa.String(length=80), nullable=False),
        sa.Column('subject_type', sa.String(length=40), nullable=False),
        sa.Column('subject_id', sa.String(length=80), nullable=True),
        sa.Column('subject_key', sa.String(length=160), nullable=False),
        sa.Column('product_date', sa.Date(), nullable=False),
        sa.Column('claim_template_id', sa.String(length=120), nullable=False),
        sa.Column('rendered_claim', sa.Text(), nullable=False),
        sa.Column('rule_id', sa.String(length=120), nullable=False),
        sa.Column('rule_version', sa.Integer(), nullable=False),
        sa.Column('rule_definition_hash', sa.String(length=64), nullable=False),
        sa.Column('typed_cited_inputs', sa.JSON(), nullable=False),
        sa.Column('computation_trace', sa.JSON(), nullable=False),
        sa.Column('completeness_state', sa.String(length=20), nullable=False),
        sa.Column('reason_codes', sa.JSON(), nullable=True),
        sa.Column('limitations', sa.JSON(), nullable=True),
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
        sa.Column('superseded_by_evidence_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "completeness_state IN ('complete', 'partial', 'unknown', 'conflict', 'withheld')",
            name='ck_evidence_objects_completeness_state',
        ),
        sa.CheckConstraint(
            "posture IN ('internal_only', 'public_candidate')",
            name='ck_evidence_objects_posture',
        ),
        sa.CheckConstraint(
            "recompute_status IN ('current', 'recompute_needed', 'recomputed', 'superseded')",
            name='ck_evidence_objects_recompute_status',
        ),
        sa.ForeignKeyConstraint(['superseded_by_evidence_id'], ['evidence_objects.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('evidence_key', name='uq_evidence_objects_evidence_key'),
    )
    op.create_index(
        'ix_evidence_objects_posture',
        'evidence_objects',
        ['posture'],
        unique=False,
    )
    op.create_index(
        'ix_evidence_objects_recompute_status',
        'evidence_objects',
        ['recompute_status'],
        unique=False,
    )
    op.create_index(
        'ix_evidence_objects_rule',
        'evidence_objects',
        ['rule_id', 'rule_version'],
        unique=False,
    )
    op.create_index(
        'ix_evidence_objects_subject_date',
        'evidence_objects',
        ['subject_type', 'subject_key', 'product_date'],
        unique=False,
    )

    op.create_table(
        'evidence_citations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('evidence_object_id', sa.Integer(), nullable=False),
        sa.Column('source_family', sa.String(length=80), nullable=False),
        sa.Column('source_table', sa.String(length=80), nullable=False),
        sa.Column('source_pk', sa.String(length=120), nullable=False),
        sa.Column('source_field_names', sa.JSON(), nullable=False),
        sa.Column('citation_role', sa.String(length=60), nullable=False),
        sa.Column('cited_values', sa.JSON(), nullable=True),
        sa.Column('provenance', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['evidence_object_id'], ['evidence_objects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_evidence_citations_object',
        'evidence_citations',
        ['evidence_object_id'],
        unique=False,
    )
    op.create_index(
        'ix_evidence_citations_source_family',
        'evidence_citations',
        ['source_family'],
        unique=False,
    )
    op.create_index(
        'ix_evidence_citations_source_row',
        'evidence_citations',
        ['source_table', 'source_pk'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_evidence_citations_source_row', table_name='evidence_citations')
    op.drop_index('ix_evidence_citations_source_family', table_name='evidence_citations')
    op.drop_index('ix_evidence_citations_object', table_name='evidence_citations')
    op.drop_table('evidence_citations')
    op.drop_index('ix_evidence_objects_subject_date', table_name='evidence_objects')
    op.drop_index('ix_evidence_objects_rule', table_name='evidence_objects')
    op.drop_index('ix_evidence_objects_recompute_status', table_name='evidence_objects')
    op.drop_index('ix_evidence_objects_posture', table_name='evidence_objects')
    op.drop_table('evidence_objects')

"""add transaction rehab assignment authority

Revision ID: e4b7c9d2a6f1
Revises: d8a2e4f6b9c1
Create Date: 2026-08-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e4b7c9d2a6f1'
down_revision = 'd8a2e4f6b9c1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('player_transactions', sa.Column(
        'transaction_subtype', sa.String(length=40), nullable=True,
    ))
    op.add_column('player_transactions', sa.Column(
        'transaction_materiality', sa.String(length=20), nullable=False,
        server_default='unresolved',
    ))
    op.add_column('player_transactions', sa.Column(
        'subtype_status', sa.String(length=20), nullable=False,
        server_default='unresolved',
    ))
    op.add_column('player_transactions', sa.Column(
        'subtype_authority', sa.String(length=60), nullable=False,
        server_default='unresolved',
    ))
    op.add_column('player_transactions', sa.Column(
        'subtype_reason_code', sa.String(length=80), nullable=False,
        server_default='legacy_unclassified',
    ))
    op.add_column('player_transactions', sa.Column(
        'subtype_evidence', sa.JSON(), nullable=True,
    ))
    op.create_check_constraint(
        'ck_player_transactions_subtype_status',
        'player_transactions',
        "subtype_status IN ('certified', 'not_certified', 'unresolved')",
    )
    op.create_check_constraint(
        'ck_player_transactions_materiality',
        'player_transactions',
        "transaction_materiality IN ('non_material', 'unresolved')",
    )


def downgrade():
    op.drop_constraint(
        'ck_player_transactions_materiality',
        'player_transactions',
        type_='check',
    )
    op.drop_constraint(
        'ck_player_transactions_subtype_status',
        'player_transactions',
        type_='check',
    )
    op.drop_column('player_transactions', 'subtype_evidence')
    op.drop_column('player_transactions', 'subtype_reason_code')
    op.drop_column('player_transactions', 'subtype_authority')
    op.drop_column('player_transactions', 'subtype_status')
    op.drop_column('player_transactions', 'transaction_materiality')
    op.drop_column('player_transactions', 'transaction_subtype')

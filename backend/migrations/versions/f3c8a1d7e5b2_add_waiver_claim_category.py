"""add waiver claim transaction category

Revision ID: f3c8a1d7e5b2
Revises: e4b7c9d2a6f1
Create Date: 2026-08-22 00:00:00.000000
"""

from alembic import op


revision = 'f3c8a1d7e5b2'
down_revision = 'e4b7c9d2a6f1'
branch_labels = None
depends_on = None


OLD_CATEGORIES = (
    "'recall', 'option', 'il_placement', 'il_activation', "
    "'roster_activation', 'roster_deactivation', 'trade', 'dfa', "
    "'outright', 'release', 'contract_selection', 'suspension', "
    "'bereavement', 'paternity', 'restricted', 'unknown'"
)
NEW_CATEGORIES = (
    "'recall', 'option', 'il_placement', 'il_activation', "
    "'roster_activation', 'roster_deactivation', 'trade', 'dfa', "
    "'outright', 'release', 'contract_selection', 'suspension', "
    "'bereavement', 'paternity', 'restricted', 'waiver_claim', 'unknown'"
)


def upgrade():
    op.drop_constraint(
        'ck_player_transactions_normalized_category',
        'player_transactions',
        type_='check',
    )
    op.create_check_constraint(
        'ck_player_transactions_normalized_category',
        'player_transactions',
        f'normalized_category IN ({NEW_CATEGORIES})',
    )


def downgrade():
    op.execute(
        "UPDATE player_transactions SET normalized_category = 'unknown', "
        "roster_snapshot_alignment = 'not_applicable', "
        "alignment_reason_code = 'unknown_transaction_category', "
        "explanatory_linkage_eligible = false "
        "WHERE normalized_category = 'waiver_claim'"
    )
    op.drop_constraint(
        'ck_player_transactions_normalized_category',
        'player_transactions',
        type_='check',
    )
    op.create_check_constraint(
        'ck_player_transactions_normalized_category',
        'player_transactions',
        f'normalized_category IN ({OLD_CATEGORIES})',
    )

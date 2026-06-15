"""enforce innings outs integrity

Revision ID: b42f7c9a1d6e
Revises: 91c4a77f2d9b
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b42f7c9a1d6e'
down_revision = '91c4a77f2d9b'
branch_labels = None
depends_on = None


def _scalar(sql):
    return op.get_bind().execute(sa.text(sql)).scalar()


def upgrade():
    null_outs = _scalar(
        """
        SELECT COUNT(*)
        FROM game_logs
        WHERE innings_pitched_outs IS NULL
        """
    )
    if null_outs:
        raise RuntimeError(
            f'Cannot enforce innings outs integrity while {null_outs} game_logs rows have null outs'
        )

    drifting_rows = _scalar(
        """
        SELECT COUNT(*)
        FROM game_logs
        WHERE innings_pitched IS NULL
           OR abs(innings_pitched - (innings_pitched_outs / 3.0)) >= 0.000001
        """
    )
    if drifting_rows:
        raise RuntimeError(
            f'Cannot enforce innings outs integrity while {drifting_rows} game_logs rows drift from outs'
        )

    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_game_logs_innings_pitched_outs_nonnegative',
            type_='check',
        )
        batch_op.alter_column(
            'innings_pitched',
            existing_type=sa.Float(),
            nullable=False,
        )
        batch_op.alter_column(
            'innings_pitched_outs',
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            'ck_game_logs_innings_pitched_outs_nonnegative',
            'innings_pitched_outs >= 0',
        )
        batch_op.create_check_constraint(
            'ck_game_logs_innings_pitched_matches_outs',
            'innings_pitched IS NOT NULL AND abs(innings_pitched - (innings_pitched_outs / 3.0)) < 0.000001',
        )


def downgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_game_logs_innings_pitched_matches_outs',
            type_='check',
        )
        batch_op.drop_constraint(
            'ck_game_logs_innings_pitched_outs_nonnegative',
            type_='check',
        )
        batch_op.alter_column(
            'innings_pitched_outs',
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.alter_column(
            'innings_pitched',
            existing_type=sa.Float(),
            nullable=True,
        )
        batch_op.create_check_constraint(
            'ck_game_logs_innings_pitched_outs_nonnegative',
            'innings_pitched_outs IS NULL OR innings_pitched_outs >= 0',
        )

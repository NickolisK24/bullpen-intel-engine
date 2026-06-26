"""add completed game contexts

Revision ID: b9e4c1f7a2d6
Revises: e7d2c9a4b6f1
Create Date: 2026-06-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b9e4c1f7a2d6'
down_revision = 'e7d2c9a4b6f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'completed_game_contexts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('game_date', sa.Date(), nullable=True),
        sa.Column('opponent_team_id', sa.Integer(), nullable=True),
        sa.Column('opponent_name', sa.String(length=100), nullable=True),
        sa.Column('home_away', sa.String(length=10), nullable=True),
        sa.Column('final_score_for', sa.Integer(), nullable=True),
        sa.Column('final_score_against', sa.Integer(), nullable=True),
        sa.Column('starter_player_id', sa.Integer(), nullable=True),
        sa.Column('starter_name', sa.String(length=100), nullable=True),
        sa.Column('starter_ip', sa.Float(), nullable=True),
        sa.Column('starter_pitch_count', sa.Integer(), nullable=True),
        sa.Column('starter_exit_inning', sa.Integer(), nullable=True),
        sa.Column('starter_exit_score_for', sa.Integer(), nullable=True),
        sa.Column('starter_exit_score_against', sa.Integer(), nullable=True),
        sa.Column('bullpen_entry_inning', sa.Integer(), nullable=True),
        sa.Column('bullpen_entry_score_for', sa.Integer(), nullable=True),
        sa.Column('bullpen_entry_score_against', sa.Integer(), nullable=True),
        sa.Column('lead_when_bullpen_entered', sa.Integer(), nullable=True),
        sa.Column('deficit_when_bullpen_entered', sa.Integer(), nullable=True),
        sa.Column('largest_lead', sa.Integer(), nullable=True),
        sa.Column('largest_deficit', sa.Integer(), nullable=True),
        sa.Column('late_runs_allowed', sa.Integer(), nullable=True),
        sa.Column('runs_allowed_innings_7_to_9', sa.Integer(), nullable=True),
        sa.Column('lead_protected', sa.Boolean(), nullable=True),
        sa.Column('lead_lost', sa.Boolean(), nullable=True),
        sa.Column('comeback_completed', sa.Boolean(), nullable=True),
        sa.Column('turning_inning', sa.Integer(), nullable=True),
        sa.Column('game_shape_created', sa.String(length=40), nullable=True),
        sa.Column('game_shape_protected', sa.Boolean(), nullable=True),
        sa.Column('bullpen_story_tag', sa.String(length=40), nullable=True),
        sa.Column('confidence', sa.String(length=10), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'team_id', 'game_pk', name='uq_completed_game_contexts_team_game'
        ),
    )
    with op.batch_alter_table('completed_game_contexts', schema=None) as batch_op:
        batch_op.create_index(
            'ix_completed_game_contexts_team_date',
            ['team_id', 'game_date'],
            unique=False,
        )
        batch_op.create_index(
            'ix_completed_game_contexts_game_pk',
            ['game_pk'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('completed_game_contexts', schema=None) as batch_op:
        batch_op.drop_index('ix_completed_game_contexts_game_pk')
        batch_op.drop_index('ix_completed_game_contexts_team_date')
    op.drop_table('completed_game_contexts')

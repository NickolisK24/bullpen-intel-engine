"""enforce game log uniqueness (pitcher_id, mlb_game_pk)

Revision ID: 9f3c1a7b2d4e
Revises: 018704c8d5fe
Create Date: 2026-06-01 00:00:00.000000

Adds a database-level unique constraint so duplicate game logs are impossible,
not merely avoided by application code.

Duplicate-handling strategy: a duplicate (pitcher_id, mlb_game_pk) row is, by
definition, the same pitching appearance ingested twice. Before adding the
constraint we DETECT and REPORT any such groups (printed to the migration
output), then keep the earliest row (MIN(id)) per group and remove the
redundant copies. Nothing references game_logs.id, so removing redundant rows
is safe and simply undoes accidental double-counting. If no duplicates exist
(the expected case), this is a no-op and only the constraint is added.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f3c1a7b2d4e'
down_revision = '018704c8d5fe'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1) Detect + report duplicates before enforcing uniqueness.
    dupes = conn.execute(sa.text("""
        SELECT pitcher_id, mlb_game_pk, COUNT(*) AS n, MIN(id) AS keep_id
        FROM game_logs
        GROUP BY pitcher_id, mlb_game_pk
        HAVING COUNT(*) > 1
        ORDER BY pitcher_id, mlb_game_pk
    """)).fetchall()

    if dupes:
        total_extra = sum(row.n - 1 for row in dupes)
        print(f"[migration 9f3c1a7b2d4e] Found {len(dupes)} duplicated "
              f"(pitcher_id, mlb_game_pk) group(s); removing {total_extra} "
              f"redundant row(s), keeping the earliest id in each group:", flush=True)
        for row in dupes:
            print(f"[migration 9f3c1a7b2d4e]   pitcher_id={row.pitcher_id} "
                  f"mlb_game_pk={row.mlb_game_pk} count={row.n} keep_id={row.keep_id}",
                  flush=True)

        # 2) Remove the redundant copies, keeping the earliest row per group.
        conn.execute(sa.text("""
            DELETE FROM game_logs g
            USING (
                SELECT pitcher_id, mlb_game_pk, MIN(id) AS keep_id
                FROM game_logs
                GROUP BY pitcher_id, mlb_game_pk
                HAVING COUNT(*) > 1
            ) d
            WHERE g.pitcher_id = d.pitcher_id
              AND g.mlb_game_pk = d.mlb_game_pk
              AND g.id <> d.keep_id
        """))
    else:
        print("[migration 9f3c1a7b2d4e] No duplicate game logs found — "
              "adding unique constraint only.", flush=True)

    # 3) Enforce uniqueness going forward.
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_game_logs_pitcher_game',
                                          ['pitcher_id', 'mlb_game_pk'])


def downgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_game_logs_pitcher_game', type_='unique')

"""widen tonight snapshot source

Revision ID: c7f1b408d93a
Revises: b9d4e17c3a80
Create Date: 2026-08-02 00:00:00.000000

The 14:00 UTC morning slate lane failed on every run. The schedule request
itself succeeded — ``/schedule`` returned HTTP 200 and the rows committed — and
then persisting the Tonight snapshot raised

    psycopg2.errors.StringDataRightTruncation:
    value too long for type character varying(40)

on the UPDATE of ``tonight_intelligence_snapshots``. The stored provenance the
lane composes is ``github_actions_morning:schedule_coherence``: 41 characters
against a 40-character column.

The failure was structural, not specific to one workflow input. The same lane's
default source composes to ``morning_slate_schedule:schedule_coherence``, also
41 characters, so any caller of this path was one character over.

This widens the column to 128 so the complete value is storable. The repair is
capacity, not truncation: shortening the workflow's source or clipping the
composed value would have made the symptom disappear while destroying the
provenance the column exists to record.

Purely a type widening:

  * no row is read, rewritten, or deleted;
  * nullability, defaults, indexes, and every unrelated column are untouched;
  * widening a varchar is a catalog-only change on PostgreSQL — no table
    rewrite and no scan.

The downgrade refuses rather than corrupting. Narrowing back to 40 would
silently truncate any value the widened column now legitimately holds, so it
checks first and fails with a clear message when such a row exists.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7f1b408d93a'
down_revision = 'b9d4e17c3a80'
branch_labels = None
depends_on = None


TABLE = 'tonight_intelligence_snapshots'
COLUMN = 'source'
# Stated here in DDL terms because a migration must be self-contained and must
# not import application code. ``models.tonight_intelligence_snapshot``
# declares the same width as TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH, and a
# PostgreSQL test asserts the live column matches that constant, so the two are
# checked against each other rather than merely intended to agree.
WIDENED_LENGTH = 128
PREVIOUS_LENGTH = 40


def upgrade():
    op.alter_column(
        TABLE,
        COLUMN,
        existing_type=sa.String(length=PREVIOUS_LENGTH),
        type_=sa.String(length=WIDENED_LENGTH),
        existing_nullable=False,
    )


def downgrade():
    conn = op.get_bind()
    oversized = conn.execute(
        sa.text(
            f'SELECT COUNT(*) FROM {TABLE} '
            f'WHERE char_length({COLUMN}) > :limit'
        ),
        {'limit': PREVIOUS_LENGTH},
    ).scalar()
    if oversized:
        raise RuntimeError(
            f'Refusing to narrow {TABLE}.{COLUMN} to '
            f'VARCHAR({PREVIOUS_LENGTH}): {oversized} row(s) hold a longer '
            f'value and would be silently truncated. Reconcile or remove those '
            f'rows before downgrading.'
        )
    op.alter_column(
        TABLE,
        COLUMN,
        existing_type=sa.String(length=WIDENED_LENGTH),
        type_=sa.String(length=PREVIOUS_LENGTH),
        existing_nullable=False,
    )

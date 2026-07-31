#!/usr/bin/env python
"""The complete Foundation 3C governed bootstrap scope, defined once.

Stage E verifies the whole 109-game bootstrap rather than any one rollout
increment. That population is the union of three reviewed sets:

  original five   the first controlled write
  R4 five         the second controlled write
  R5/R6 ninety-nine   the remaining window

The ninety-nine are IMPORTED from `r5_remaining_window_scope`, never restated.
A second handwritten copy of those identifiers is a second thing that can be
wrong, and the two copies would agree right up until the moment one of them
mattered.

The scope is hard-coded and repository-pinned. It is not read from the database,
an API, a workflow input, an environment variable, or a previous run's artifact.
The production database VERIFIES this set; it never defines it.

TEMPORARY. This module exists to support the Stage E closeout verification and
is retained only until Stage E2 removes it along with the Stage E workflow.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import r5_remaining_window_scope as remaining  # noqa: E402


REFERENCE_DATE = remaining.REFERENCE_DATE

# ── The two completed controlled-write sets ────────────────────────────────
ORIGINAL_COMPLETED_GAME_PKS = remaining.ORIGINAL_COMPLETED_GAME_PKS
R4_COMPLETED_GAME_PKS = remaining.R4_COMPLETED_GAME_PKS
COMPLETED_BEFORE_R6 = remaining.COMPLETED_GAME_PKS          # the sorted ten

# ── The remaining ninety-nine, imported ────────────────────────────────────
REMAINING_GAME_PKS = remaining.CANONICAL_ORDER

# ── The complete governed bootstrap ────────────────────────────────────────
# Canonical order is chronological by rollout increment: the original five, the
# R4 five, then the reviewed 99 in their own canonical planner order. This is a
# review ordering for a read-only verification, not a write authorization.
CANONICAL_ORDER = tuple(
    list(ORIGINAL_COMPLETED_GAME_PKS)
    + list(R4_COMPLETED_GAME_PKS)
    + list(REMAINING_GAME_PKS)
)
SORTED_SET = tuple(sorted(CANONICAL_ORDER))

EXPECTED_GAME_COUNT = 109
EXPECTED_COMPLETED_COUNT = 109
EXPECTED_UNRESOLVED_COUNT = 0

# ── Expected shape, by arithmetic across the three increments ──────────────
#   original five   38 rows / 14 ignored
#   R4 five         43 rows / 18 ignored
#   R5/R6 99       865 rows / 291 ignored
ORIGINAL_COMPLETED_ROWS = remaining.ORIGINAL_COMPLETED_ROWS          # 38
ORIGINAL_COMPLETED_IGNORED = remaining.ORIGINAL_COMPLETED_IGNORED    # 14
R4_COMPLETED_ROWS = remaining.R4_COMPLETED_ROWS                      # 43
R4_COMPLETED_IGNORED = remaining.R4_COMPLETED_IGNORED                # 18
REMAINING_ROWS = remaining.EXPECTED_TOTAL_ROWS                       # 865
REMAINING_IGNORED = remaining.EXPECTED_TOTAL_IGNORED                 # 291

EXPECTED_TOTAL_ROWS = (
    ORIGINAL_COMPLETED_ROWS + R4_COMPLETED_ROWS + REMAINING_ROWS
)                                                                     # 946
EXPECTED_TOTAL_IGNORED = (
    ORIGINAL_COMPLETED_IGNORED + R4_COMPLETED_IGNORED + REMAINING_IGNORED
)                                                                     # 323

# ── R6 historical evidence ─────────────────────────────────────────────────
# Recorded so Stage E can report the delta rather than silently re-baseline.
# These are HISTORICAL values. Stage E does not require its own hashes to equal
# the R6 hashes, because legitimate current-roster synchronization may have
# happened since; it requires its own before and after to equal each other.
R6_REPOSITORY_SHA = '81271e0671b9391b4297f3b438e2a8b836bf94d7'
R6_WORKFLOW_RUN_ID = '30664706174'
R6_APPROVED_FINGERPRINT = (
    '40659a4051226df40ef7cedbca7a6bc2689d5c2bfbdd4ccdb717fc6fc0c79343'
)
R6_SCOPE_DIGEST = remaining.SCOPE_DIGEST
R6_GLOBAL_DEAD_LETTER_COUNT = 1389

R6_STATE_HASHES = {
    'game_log_content_hash':
        'a53f40addf8b818872b3a2d1c0ba88b9f2579046c54feaf49cfe7a659e33abf3',
    'canonical_outs_hash':
        'a4329604b7fdcb138f02cbd5ae6d7cc34bd120e2b6fc9ea5d1de47587854508d',
    'correction_provenance_hash':
        'dd49944590c854b557adf62824633665b8214239fdf7fd668684f8d503e3c84e',
    'appearance_team_hash':
        '6fe8523b0474f67de003b3bff46becda70720ff3f35f75e56c402f1a744c2046',
    'pitcher_state_hash':
        '009b99b589d25ac49722166ed1a125a18144063063a850a16bd134c9d60cf626',
}


def scope_digest(game_pks=SORTED_SET) -> str:
    """Order-independent identity of a game set.

    Same construction as the R5 helper so the two digests are comparable: the
    sorted identifiers, comma-joined, hashed. Order is asserted separately and
    deserves its own failure.
    """
    encoded = ','.join(str(int(game_pk)) for game_pk in sorted(game_pks))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


FULL_SCOPE_DIGEST = scope_digest()


def only_game_pk_arguments(game_pks=CANONICAL_ORDER) -> list[str]:
    """The exact `--only-game-pk` argument sequence for the full bootstrap."""
    arguments: list[str] = []
    for game_pk in game_pks:
        arguments.extend(('--only-game-pk', str(int(game_pk))))
    return arguments


def emit_arguments(target: Path) -> dict:
    """Write the pinned `--only-game-pk` sequence for the workflow to consume.

    The workflow reads THIS rather than carrying its own copy of 109
    identifiers. A second literal list would be a second thing that can drift,
    and the two would agree right up until one of them mattered. The scope is
    still repository-pinned — it comes from a module in this commit, not from
    an input, the database, an API, a prior artifact, or the network.
    """
    _assert_scope_is_coherent()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '\n'.join(only_game_pk_arguments()) + '\n', encoding='utf-8',
    )
    return {
        'game_count': len(CANONICAL_ORDER),
        'unique_game_count': len(set(CANONICAL_ORDER)),
        'full_scope_digest': FULL_SCOPE_DIGEST,
        'expected_rows': EXPECTED_TOTAL_ROWS,
        'expected_ignored': EXPECTED_TOTAL_IGNORED,
    }


def _main(argv=None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='Emit the pinned Foundation 3C Stage E bootstrap scope.',
    )
    parser.add_argument('--emit-arguments', required=True)
    parser.add_argument('--expected-digest', required=True)
    parser.add_argument('--expected-game-count', type=int, default=109)
    args = parser.parse_args(argv)

    facts = emit_arguments(Path(args.emit_arguments))
    if facts['full_scope_digest'] != args.expected_digest:
        print('::error::Stage E scope digest does not match the approved value.')
        return 1
    if facts['game_count'] != args.expected_game_count:
        print('::error::Stage E scope does not contain the approved game count.')
        return 1
    if facts['unique_game_count'] != args.expected_game_count:
        print('::error::Stage E scope contains duplicate game identifiers.')
        return 1
    print(json.dumps(facts, sort_keys=True))
    return 0


def _assert_scope_is_coherent() -> None:
    """Fail at import if these constants ever contradict each other."""
    assert len(CANONICAL_ORDER) == EXPECTED_GAME_COUNT
    assert len(set(CANONICAL_ORDER)) == EXPECTED_GAME_COUNT
    assert all(isinstance(pk, int) and pk > 0 for pk in CANONICAL_ORDER)
    assert SORTED_SET == tuple(sorted(CANONICAL_ORDER))
    # The union is exactly the ten completed plus the ninety-nine remaining.
    assert set(CANONICAL_ORDER) == (
        set(COMPLETED_BEFORE_R6) | set(REMAINING_GAME_PKS)
    )
    assert not set(COMPLETED_BEFORE_R6) & set(REMAINING_GAME_PKS)
    assert len(COMPLETED_BEFORE_R6) == 10
    assert len(REMAINING_GAME_PKS) == 99
    assert EXPECTED_TOTAL_ROWS == 946
    assert EXPECTED_TOTAL_IGNORED == 323
    assert FULL_SCOPE_DIGEST != R6_SCOPE_DIGEST  # different populations


_assert_scope_is_coherent()


if __name__ == '__main__':
    raise SystemExit(_main())

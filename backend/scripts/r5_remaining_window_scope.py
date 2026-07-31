#!/usr/bin/env python
"""The exact Foundation 3C R5 scope, defined once.

R5 runs the entire remaining bootstrap window: the 99 governed final games that
are still unresolved after R4 completed the first ten. Three separate artifacts
depend on that set being identical everywhere — the state inspector, the report
validator, and the R6 command manifest — so it is defined here once and
imported, rather than restated and quietly allowed to drift.

The set is HARD-CODED on purpose. It is not read from the database, an API, a
previous run's artifact, an environment variable, or a workflow input. The
production database is used to VERIFY this set, never to define it: a scope that
defines itself from the thing it is scoping proves nothing.

Two representations are kept because they answer different questions:

  CANONICAL_ORDER  the planner's deterministic processing sequence. Supports
                   review and lets R6 be generated against the reviewed run.
  SORTED_SET       order-independent identity. Proves scope.

The completed ten are held separately and must never enter R5's scope. Their
union with the 99 is the whole governed 109-game window, which is what makes
"the remaining window" a checkable claim rather than a description.
"""

from __future__ import annotations

import hashlib


REFERENCE_DATE = '2026-07-29'

# ── The ten games already completed and durably checkpointed ────────────────
# Five from the original controlled write, five from R4. These are EXCLUDED
# from R5 and must not appear in its scope.
ORIGINAL_COMPLETED_GAME_PKS = (823518, 824735, 823761, 824083, 824327)
R4_COMPLETED_GAME_PKS = (823110, 825055, 824004, 823438, 824408)
COMPLETED_GAME_PKS = tuple(
    sorted(ORIGINAL_COMPLETED_GAME_PKS + R4_COMPLETED_GAME_PKS)
)

# ── The 99 remaining unresolved games, in canonical processing order ────────
# This ordering is the planner's, not an arbitrary listing: it sorts by retry
# rank, criticality, represented date, game start time, then game id. Every one
# of those inputs is already fixed for a final game, so the sequence is stable
# across runs and safe to assert on.
CANONICAL_ORDER = (
    823519, 822784, 824732, 824896, 822873, 824166, 824650, 824893, 824406,
    822785, 823042, 824247, 823759, 823352, 824248, 822707, 823434, 824812,
    822952, 823601, 823843, 824733, 824573, 822872, 823680, 823031, 823196,
    824244, 822704, 823197, 823841, 824734, 823435, 822948, 823355, 824811,
    823679, 823758, 824571, 822869, 823027, 823600, 822950, 822706, 823354,
    824730, 824810, 823599, 823840, 824246, 823678, 823755, 824572, 823028,
    822870, 823194, 823433, 822868, 823353, 823839, 824245, 822705, 823597,
    824570, 823025, 824001, 824977, 823195, 824490, 822949, 823350, 823838,
    824243, 822703, 824489, 823676, 824569, 823026, 824003, 823275, 824976,
    823193, 823923, 823837, 823351, 822702, 823596, 824242, 823192, 823273,
    822947, 823598, 824487, 823677, 824567, 823022, 824002, 824973, 823924,
)

SORTED_SET = tuple(sorted(CANONICAL_ORDER))

EXPECTED_GAME_COUNT = 99
EXPECTED_COMPLETED_COUNT = 10
EXPECTED_WINDOW_COUNT = 109

# ── Expected shape, derived from the full reviewed window ───────────────────
# The 109-game window carried 946 appearance rows and 323 ignored decimal-only
# differences. The first completed five accounted for 38 rows and 14 ignored;
# the R4 five for 43 and 18. What remains is arithmetic, not an estimate.
FULL_WINDOW_GAMES = 109
FULL_WINDOW_ROWS = 946
FULL_WINDOW_IGNORED = 323

ORIGINAL_COMPLETED_ROWS = 38
ORIGINAL_COMPLETED_IGNORED = 14
R4_COMPLETED_ROWS = 43
R4_COMPLETED_IGNORED = 18

EXPECTED_TOTAL_ROWS = (
    FULL_WINDOW_ROWS - ORIGINAL_COMPLETED_ROWS - R4_COMPLETED_ROWS
)                                                                       # 865
EXPECTED_TOTAL_IGNORED = (
    FULL_WINDOW_IGNORED - ORIGINAL_COMPLETED_IGNORED - R4_COMPLETED_IGNORED
)                                                                       # 291


def scope_digest(game_pks=SORTED_SET) -> str:
    """Order-independent identity of a game set.

    Computed over the SORTED set so it answers "is this the same scope?"
    without also answering "in the same order?" — order is asserted separately
    and deserves its own failure.
    """
    encoded = ','.join(str(int(game_pk)) for game_pk in sorted(game_pks))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


SCOPE_DIGEST = scope_digest()


def only_game_pk_arguments(game_pks=CANONICAL_ORDER) -> list[str]:
    """The exact `--only-game-pk` argument sequence for this scope."""
    arguments: list[str] = []
    for game_pk in game_pks:
        arguments.extend(('--only-game-pk', str(int(game_pk))))
    return arguments


def _assert_scope_is_coherent() -> None:
    """Fail at import if the constants above ever contradict each other.

    A scope module that can be edited into an inconsistent state is not a
    single source of truth. These are the properties every consumer assumes.
    """
    assert len(CANONICAL_ORDER) == EXPECTED_GAME_COUNT
    assert len(set(CANONICAL_ORDER)) == EXPECTED_GAME_COUNT
    assert all(isinstance(pk, int) and pk > 0 for pk in CANONICAL_ORDER)
    assert len(COMPLETED_GAME_PKS) == EXPECTED_COMPLETED_COUNT
    assert len(set(COMPLETED_GAME_PKS)) == EXPECTED_COMPLETED_COUNT
    assert not set(CANONICAL_ORDER) & set(COMPLETED_GAME_PKS)
    assert (
        len(set(CANONICAL_ORDER) | set(COMPLETED_GAME_PKS))
        == EXPECTED_WINDOW_COUNT
    )
    assert SORTED_SET == tuple(sorted(CANONICAL_ORDER))
    assert EXPECTED_TOTAL_ROWS == 865
    assert EXPECTED_TOTAL_IGNORED == 291
    assert FULL_WINDOW_GAMES - 5 - 5 == EXPECTED_GAME_COUNT


_assert_scope_is_coherent()

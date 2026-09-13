"""Transaction-scoped fences for captured selector resources, not selected rows.

The two-integer advisory key space is separate from R2's one-integer game
keys and transaction namespace 509000000. Integer subject keys are lossless;
there is no process hash or truncated string hash in this protocol.
"""

from sqlalchemy import text
from sqlalchemy.orm import scoped_session

from utils.db import db


DASHBOARD = 510000001
COMPARISON = 510000002
PUBLICATION = 510000003
AUTHORITY_GROUP = {
    'live': 0, 'final': 1, 'corrected_final': 1,
    'roster_authoritative': 2, 'pregame_authoritative': 3,
}


class SelectorFenceConflict(RuntimeError):
    """The entire owner transaction must roll back and retry."""


def _owner_session(session):
    session = session if session is not None else db.session
    return session() if isinstance(session, scoped_session) else session


def predecessor_resources(authority, *, games=(), teams=(), pitchers=()):
    group = AUTHORITY_GROUP[authority]
    return tuple(sorted({
        (510000100 + group * 3 + offset, int(subject))
        for offset, subjects in enumerate((games, teams, pitchers))
        for subject in subjects
    }))


def captured_resources(context, authority):
    resources = set(predecessor_resources(
        authority, games=context.requested_game_ids,
        teams=context.requested_team_ids, pitchers=context.requested_pitcher_ids,
    ))
    # An absent dashboard is also a selector decision: insertion must fence it.
    if context.read_model_selectors:
        resources.add((DASHBOARD, 0))
        resources.add((PUBLICATION, 0))
    resources.update((COMPARISON, int(team)) for team in
                     context.manifest_value()['selectors']['legacy_comparisons'])
    return tuple(sorted(resources))


def acquire_selector_fences(resources, *, shared=False, wait=False, session=None):
    """Hold normalized locks through the caller's OUTER commit or rollback.

    Owners can already hold R2 or row locks. The default is consequently
    nonblocking, like R2's reverse-order guard: contention rejects the whole
    transaction, never waits in a reverse lock order. A caller at transaction
    entry, before other semantic/row locks, may explicitly choose waiting.
    """
    session = _owner_session(session)
    connection = session.connection()
    if connection.dialect.name != 'postgresql':
        return session.get_transaction()
    function = ('pg_advisory_xact_lock' if wait else 'pg_try_advisory_xact_lock')
    if shared:
        function += '_shared'
    for domain, key in sorted(set(resources)):
        if not (0 <= int(key) <= 2147483647):
            raise ValueError('Selector subject is outside the integer key contract.')
        accepted = connection.execute(text(
            f'SELECT {function}(:domain, :key)'
        ), {'domain': int(domain), 'key': int(key)}).scalar_one()
        if not wait and not accepted:
            raise SelectorFenceConflict(f'Selector fence busy: {domain}/{key}')
    return session.get_transaction()


def acquire_completion_fences(context, authority, *, session=None):
    session = _owner_session(session)
    connection = session.connection()
    if connection.dialect.name == 'postgresql':
        # A missing old-binary backstop must not silently become app-only proof.
        installed, isolation = connection.execute(text(
            "SELECT to_regprocedure('baseballos_guard_selector_generation()') IS NOT NULL, "
            "current_setting('transaction_isolation')"
        )).one()
        if not installed:
            raise SelectorFenceConflict('Selector generation database guard is not installed.')
        if isolation not in ('read committed', 'read uncommitted'):
            raise SelectorFenceConflict('Completion requires fresh READ COMMITTED selector reads.')
    return acquire_selector_fences(captured_resources(context, authority),
                                   shared=True, session=session)


def assert_completion_transaction(transaction, *, session=None):
    session = _owner_session(session)
    if session.get_transaction() is not transaction or not transaction.is_active:
        raise SelectorFenceConflict('Completion transaction ended during selector validation.')


def fence_dashboard_writer(snapshot_type, *, source='', session=None):
    if snapshot_type == 'bullpen_dashboard':
        resources = ((DASHBOARD, 0),)
    elif snapshot_type == 'team_board_delta':
        resources = ((COMPARISON, int(source.removeprefix('tb_delta:team:'))),)
    else:
        return
    acquire_selector_fences(resources, session=session)


def fence_comparison_writer(team_ids, *, session=None):
    acquire_selector_fences(((COMPARISON, int(team)) for team in team_ids), session=session)

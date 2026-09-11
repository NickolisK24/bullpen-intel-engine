"""Transaction-scoped semantic exclusion and immutable worker claim identity."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from models.sync_job import SyncJob
from utils.db import db
from utils.time import utc_now_naive


GAME_LOCK_NAMESPACE = 507000000000
_claim = ContextVar('semantic_writer_claim', default=None)


@dataclass(frozen=True)
class WorkerClaim:
    job_id: int
    worker_id: str
    claim_token: str


def lock_game(game_pk):
    """One game mutation lock; source acquisition need not hold this lock."""
    if db.session.get_bind().dialect.name == 'postgresql':
        session = db.session()
        connection = session.connection()
        transaction = session.get_transaction()
        prior_transaction, keys = session.info.get('semantic_game_keys', (None, set()))
        if prior_transaction is not transaction:
            keys = set()
        game_pk = int(game_pk)
        if keys and game_pk < max(keys) and game_pk not in keys:
            # Multi-game legacy callers do not all iterate in game-key order.
            # They may acquire a free lower key, but must never wait backwards.
            accepted = connection.execute(text('SELECT pg_try_advisory_xact_lock(:key)'),
                                          {'key': GAME_LOCK_NAMESPACE + game_pk}).scalar_one()
            if not accepted:
                raise RuntimeError(f'game semantic fence busy: {game_pk}')
        else:
            connection.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                               {'key': GAME_LOCK_NAMESPACE + game_pk})
        keys.add(game_pk)
        session.info['semantic_game_keys'] = (transaction, keys)


def authorize_roster_projection(team_id):
    """Scoped transaction marker consumed by the deployed-binary DB backstop."""
    from services.mlb_club_directory import MLB_TEAM_IDS
    if int(team_id) not in MLB_TEAM_IDS:
        raise ValueError('Only an MLB club may own the roster projection.')
    db.session.flush()
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text(
            "SELECT set_config('baseballos.roster_owner', :team, true)"
        ), {'team': str(int(team_id))})


def authorize_final_projection(game_pk):
    """Called only after SP-07 has validated its sources under the game lock."""
    session = db.session()
    session.flush()
    session.info['final_projection_owner'] = (session.get_transaction(), int(game_pk))
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text(
            "SELECT set_config('baseballos.final_game_owner', :game, true)"
        ), {'game': str(int(game_pk))})


def owns_final_projection(game_pk):
    session = db.session()
    return session.info.get('final_projection_owner') == (session.get_transaction(), int(game_pk))


def authorize_observation_projection(game_pk):
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text(
            "SELECT set_config('baseballos.observation_owner', :game, true)"
        ), {'game': str(int(game_pk))})


def lock_transaction(transaction_key):
    if db.session.get_bind().dialect.name == 'postgresql':
        session = db.session()
        connection = session.connection()
        transaction = session.get_transaction()
        prior_transaction, keys = session.info.get('semantic_transaction_keys', (None, set()))
        if prior_transaction is not transaction:
            keys = set()
        if keys and transaction_key < max(keys) and transaction_key not in keys:
            accepted = connection.execute(text(
                'SELECT pg_try_advisory_xact_lock(509000000, hashtext(:key))'
            ), {'key': transaction_key}).scalar_one()
            if not accepted:
                raise RuntimeError(f'transaction semantic fence busy: {transaction_key}')
        else:
            connection.execute(text('SELECT pg_advisory_xact_lock(509000000, hashtext(:key))'),
                               {'key': transaction_key})
        keys.add(transaction_key)
        session.info['semantic_transaction_keys'] = (transaction, keys)


def authorize_transaction_projection(transaction_key):
    # Complete the prior event while its scoped marker is still installed.
    db.session.flush()
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text(
            "SELECT set_config('baseballos.transaction_owner', :key, true)"
        ), {'key': transaction_key})


def authorize_schedule_projection(game_pks):
    keys = sorted(set(map(int, game_pks)))
    for key in keys:
        lock_game(key)
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text(
            "SELECT set_config('baseballos.schedule_owners', :keys, true)"
        ), {'keys': json.dumps([str(key) for key in keys])})


@contextmanager
def worker_claim(job_id, worker_id, claim_token):
    """Capture credentials before ORM expiration can reload another claim."""
    token = _claim.set(WorkerClaim(int(job_id), worker_id, claim_token))
    try:
        yield
    finally:
        _claim.reset(token)


def validate_worker_claim(session):
    claim = _claim.get()
    if claim is None:
        return
    # Core column results bypass the ORM identity map. The queue row stays
    # locked in this transaction, including during the final semantic flush.
    connection = session.connection()
    row = connection.execute(select(
        SyncJob.status, SyncJob.worker_id, SyncJob.claim_token, SyncJob.lease_until,
    ).where(SyncJob.id == claim.job_id).with_for_update()).one_or_none()
    from services.sync_jobs import LeaseExpiredError, LeaseOwnershipError

    if row is None or (row.status, row.worker_id, row.claim_token) != (
        'running', claim.worker_id, claim.claim_token,
    ):
        raise LeaseOwnershipError('Semantic writer no longer owns its original claim.')
    now = (
        connection.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
        if connection.dialect.name == 'postgresql' else utc_now_naive()
    )
    if row.lease_until is None or row.lease_until <= now:
        raise LeaseExpiredError('Semantic writer lease expired before transaction commit.')


@event.listens_for(Session, 'before_commit')
def _fence_owner_commit(session):
    if not session.in_nested_transaction():
        validate_worker_claim(session)

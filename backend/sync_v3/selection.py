"""Advance or recover the disposable historical core selector."""
from sync_v3.generation import _inspect
from sync_v3.history import _transaction


class SelectionWithheld(ValueError):
    def __init__(self, review):
        self.review = review
        super().__init__(f"Historical selection withheld: {review['status']} {review['reason_codes']}")


def select_generation(connection, digest, *, expected_revision, rollback=False):
    """Compare and exchange an isolated historical selection under one serializable view."""
    if type(expected_revision) is not int or expected_revision < 0 or type(rollback) is not bool:
        raise ValueError('Expected a nonnegative selector revision and explicit rollback mode')
    if digest is None and not rollback:
        raise ValueError('A candidate generation is required')
    action = 'rollback' if rollback else 'select'
    return _transaction(connection, _select, digest, expected_revision, action)


def _select(cur, digest, expected, action):
    cur.execute("SELECT current_user,current_database(),inet_server_addr()")
    if cur.fetchone() != ('sync_v3_reviewer', 'sync_v3_rehearsal', None):
        raise PermissionError('Historical selection requires the isolated rehearsal reviewer')
    cur.execute("SELECT revision,generation,action FROM candidate.core_selections ORDER BY revision DESC LIMIT 1")
    last = cur.fetchone()
    if last == (expected+1, digest, action):
        return expected+1
    if (last[0] if last else 0) != expected:
        raise ValueError('Historical selection predecessor changed')
    if digest is not None:
        result = _inspect(cur, digest, compare_latest=(action == 'select'))
        review = result['selection_review'] if action == 'select' else result['core_candidate_review']
        if review['status'] != 'core_comparison_complete':
            raise SelectionWithheld(review)
    cur.execute('SELECT candidate.record_core_selection(%s,%s,%s)', (expected, digest, action))
    return cur.fetchone()[0]

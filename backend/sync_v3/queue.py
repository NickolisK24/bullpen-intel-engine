"""Transactional candidate jobs. Each public operation uses its caller's transaction."""

from datetime import timedelta
import uuid

from psycopg2.extras import Json


def enqueue(cur, identity, payload, now, *, budget='current', priority=100,
            prerequisite=None, max_attempts=3):
    cur.execute("""INSERT INTO candidate.jobs(identity,payload,priority,budget,prerequisite,
                    available_at,max_attempts) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (identity) DO NOTHING RETURNING id""",
                (identity, Json(payload), priority, budget, prerequisite, now, max_attempts))
    created = cur.fetchone()
    if created:
        return created[0]
    cur.execute("""SELECT id FROM candidate.jobs WHERE identity=%s AND payload=%s
                   AND budget=%s AND priority=%s AND prerequisite IS NOT DISTINCT FROM %s
                   AND max_attempts=%s""",
                (identity, Json(payload), budget, priority, prerequisite, max_attempts))
    existing = cur.fetchone()
    if not existing:
        raise ValueError('Job identity reused for different work')
    return existing[0]


def claim(cur, now, *, budget='current', lease=timedelta(minutes=5)):
    if not timedelta(0) < lease <= timedelta(hours=1):
        raise ValueError('Invalid job lease')
    # Bound the amount of recovery a single invocation can perform.
    for _ in range(16):
        cur.execute("""SELECT j.id,j.payload,j.token,j.attempts,j.max_attempts
                       FROM candidate.jobs j
                       WHERE j.budget=%s AND ((j.state='pending' AND j.available_at<=%s)
                       OR (j.state='running' AND j.lease_until<=%s)) AND
                       (j.prerequisite IS NULL OR EXISTS (SELECT 1 FROM candidate.jobs p
                         WHERE p.id=j.prerequisite AND p.state='done'))
                       ORDER BY j.priority,j.available_at,j.id LIMIT 1 FOR UPDATE OF j SKIP LOCKED""",
                    (budget, now, now))
        row = cur.fetchone()
        if not row:
            return None
        job_id, payload, old_token, attempts, maximum = row
        if old_token:
            cur.execute("""UPDATE candidate.attempts SET finished_at=%s,outcome='expired'
                           WHERE token=%s AND finished_at IS NULL""", (now, old_token))
        if attempts >= maximum:
            cur.execute("UPDATE candidate.jobs SET state='dead',token=NULL,lease_until=NULL WHERE id=%s",
                        (job_id,))
            continue
        token = str(uuid.uuid4())
        cur.execute("""UPDATE candidate.jobs SET state='running',attempts=attempts+1,token=%s,
                       lease_until=%s WHERE id=%s""", (token, now + lease, job_id))
        cur.execute('INSERT INTO candidate.attempts(token,job_id,claimed_at) VALUES (%s,%s,%s)',
                    (token, job_id, now))
        return job_id, token, payload
    return None


def settle(cur, job_id, token, now, *, error=False, retryable=True):
    """Call in the same transaction as the candidate effects, raising rolls both back."""
    cur.execute("""SELECT attempts,max_attempts FROM candidate.jobs
                   WHERE id=%s AND state='running' AND token=%s AND lease_until>%s
                   FOR UPDATE""", (job_id, token, now))
    row = cur.fetchone()
    if not row:
        raise ValueError('Expired or superseded job claim')
    attempts, maximum = row
    state, outcome, available = 'done', 'done', now
    if error:
        state, outcome = 'dead', 'dead'
        if retryable and attempts < maximum:
            state, outcome = 'pending', 'retry'
            available += timedelta(seconds=min(3600, 30 * 2 ** min(attempts - 1, 7)))
    cur.execute("""UPDATE candidate.jobs SET state=%s,available_at=%s,token=NULL,lease_until=NULL
                   WHERE id=%s""", (state, available, job_id))
    cur.execute('UPDATE candidate.attempts SET outcome=%s,finished_at=%s WHERE token=%s',
                (outcome, now, token))

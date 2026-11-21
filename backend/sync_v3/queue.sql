CREATE TABLE candidate.jobs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identity text NOT NULL UNIQUE,
    payload jsonb NOT NULL,
    priority integer NOT NULL CHECK (priority >= 0),
    budget text NOT NULL CHECK (budget IN ('current','historical')),
    prerequisite bigint REFERENCES candidate.jobs(id),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','running','done','dead')),
    available_at timestamptz NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL CHECK (max_attempts > 0),
    token uuid,
    lease_until timestamptz,
    CHECK ((state='running') = (token IS NOT NULL)),
    CHECK ((state='running') = (lease_until IS NOT NULL))
);
CREATE INDEX jobs_ready ON candidate.jobs(budget,priority,available_at,id) WHERE state='pending';
CREATE INDEX jobs_expired ON candidate.jobs(budget,lease_until,id) WHERE state='running';
CREATE TABLE candidate.attempts (
    token uuid PRIMARY KEY,
    job_id bigint NOT NULL REFERENCES candidate.jobs(id),
    claimed_at timestamptz NOT NULL,
    finished_at timestamptz,
    outcome text CHECK (outcome IN ('done','retry','dead','expired')),
    CHECK ((finished_at IS NULL) = (outcome IS NULL))
);
GRANT SELECT, INSERT, UPDATE ON candidate.jobs, candidate.attempts TO sync_v3_worker;
CREATE INDEX jobs_pending_request ON candidate.jobs(budget,md5(payload::text)) WHERE state='pending';

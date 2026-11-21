CREATE TABLE candidate.revisions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain text NOT NULL,
    identity text NOT NULL,
    revision integer NOT NULL CHECK (revision>0),
    predecessor bigint REFERENCES candidate.revisions(id),
    source_id bigint NOT NULL REFERENCES candidate.fetches(id),
    context_id bigint REFERENCES candidate.fetches(id),
    observed_at timestamptz NOT NULL,
    facts jsonb NOT NULL,
    UNIQUE(domain,identity,revision)
);
CREATE TABLE candidate.confirmations (
    domain text NOT NULL,
    identity text NOT NULL,
    source_id bigint NOT NULL REFERENCES candidate.fetches(id),
    context_id bigint REFERENCES candidate.fetches(id),
    revision_id bigint NOT NULL REFERENCES candidate.revisions(id),
    observed_at timestamptz NOT NULL,
    PRIMARY KEY(domain,identity,source_id)
);
CREATE INDEX confirmations_by_subject ON candidate.confirmations(domain,identity,observed_at DESC,source_id DESC);
GRANT SELECT,INSERT ON candidate.revisions,candidate.confirmations TO sync_v3_worker;

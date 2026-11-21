CREATE TABLE candidate.payloads (
    sha256 text PRIMARY KEY CHECK (length(sha256)=64),
    encoded_json bytea NOT NULL
);
CREATE TABLE candidate.fetches (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token uuid NOT NULL UNIQUE REFERENCES candidate.attempts(token),
    endpoint text NOT NULL,
    parameters jsonb NOT NULL,
    received_at timestamptz NOT NULL,
    sha256 text REFERENCES candidate.payloads(sha256),
    outcome text NOT NULL CHECK (outcome IN ('received','invalid','failed')),
    reason text,
    CHECK (outcome='failed' OR sha256 IS NOT NULL)
);
CREATE INDEX fetches_by_subject ON candidate.fetches(endpoint,parameters,received_at DESC,id DESC);
GRANT SELECT, INSERT ON candidate.payloads, candidate.fetches TO sync_v3_worker;

CREATE TABLE candidate.refusals (
    source_id bigint PRIMARY KEY REFERENCES candidate.fetches(id),
    reason text NOT NULL
);
GRANT SELECT,INSERT ON candidate.refusals TO sync_v3_worker;

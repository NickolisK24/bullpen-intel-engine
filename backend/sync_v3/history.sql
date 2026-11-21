CREATE TABLE candidate.workload_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject text NOT NULL CHECK (subject IN ('team','pitcher')),
    mlb_id integer NOT NULL CHECK (mlb_id > 0),
    represented date NOT NULL,
    methodology text NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    predecessor bigint UNIQUE REFERENCES candidate.workload_history(id),
    semantic_digest text NOT NULL CHECK (length(semantic_digest) = 64),
    input_digest text NOT NULL CHECK (length(input_digest) = 64),
    facts jsonb NOT NULL,
    UNIQUE(subject, mlb_id, represented, methodology, revision),
    CHECK ((revision = 1) = (predecessor IS NULL))
);
CREATE TABLE candidate.workload_history_sources (
    snapshot bigint NOT NULL REFERENCES candidate.workload_history(id),
    source_id bigint NOT NULL REFERENCES candidate.fetches(id),
    PRIMARY KEY (snapshot, source_id)
);
GRANT SELECT, INSERT ON candidate.workload_history, candidate.workload_history_sources TO sync_v3_worker;
CREATE INDEX workload_history_by_date ON candidate.workload_history(methodology, represented);

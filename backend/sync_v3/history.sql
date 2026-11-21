CREATE TABLE candidate.workload_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject text NOT NULL CHECK (subject IN ('team','pitcher','game')),
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

CREATE TABLE candidate.history_requests (
    snapshot bigint NOT NULL REFERENCES candidate.workload_history(id),
    endpoint text NOT NULL,
    parameters jsonb NOT NULL,
    PRIMARY KEY (snapshot, endpoint, parameters)
);
CREATE INDEX history_requests_by_source ON candidate.history_requests(endpoint, parameters, snapshot);
GRANT SELECT, INSERT ON candidate.history_requests TO sync_v3_worker;

CREATE TABLE candidate.change_inputs (
    change_snapshot bigint NOT NULL REFERENCES candidate.workload_history(id),
    input_snapshot bigint NOT NULL REFERENCES candidate.workload_history(id),
    PRIMARY KEY (change_snapshot, input_snapshot),
    CHECK (change_snapshot <> input_snapshot)
);
GRANT SELECT, INSERT ON candidate.change_inputs TO sync_v3_worker;

CREATE TABLE candidate.generations (
    creation_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
    digest text PRIMARY KEY CHECK (length(digest) = 64),
    represented date NOT NULL,
    manifest jsonb NOT NULL
);
CREATE TABLE candidate.generation_inputs (
    generation text NOT NULL REFERENCES candidate.generations(digest),
    snapshot bigint NOT NULL REFERENCES candidate.workload_history(id),
    PRIMARY KEY (generation, snapshot)
);
GRANT SELECT ON candidate.generations TO sync_v3_worker;
GRANT INSERT (digest,represented,manifest) ON candidate.generations TO sync_v3_worker;
GRANT SELECT, INSERT ON candidate.generation_inputs TO sync_v3_worker;
CREATE TABLE candidate.generation_sources (
    generation text NOT NULL REFERENCES candidate.generations(digest),
    source bigint NOT NULL REFERENCES candidate.fetches(id),
    PRIMARY KEY (generation, source)
);
GRANT SELECT, INSERT ON candidate.generation_sources TO sync_v3_worker;

CREATE FUNCTION candidate.require_generation_build_transaction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM candidate.generations
                   WHERE digest=NEW.generation AND creation_xid=pg_current_xact_id()) THEN
        RAISE EXCEPTION 'Candidate generation membership is sealed';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER seal_generation_inputs BEFORE INSERT ON candidate.generation_inputs
    FOR EACH ROW EXECUTE FUNCTION candidate.require_generation_build_transaction();
CREATE TRIGGER seal_generation_sources BEFORE INSERT ON candidate.generation_sources
    FOR EACH ROW EXECUTE FUNCTION candidate.require_generation_build_transaction();

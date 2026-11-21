CREATE TABLE candidate.public_identity_export (
    digest text PRIMARY KEY CHECK (length(digest)=64),
    observed_at timestamptz NOT NULL UNIQUE,
    payload jsonb NOT NULL
);
CREATE TABLE candidate.public_pitcher_identity (
    mlb_id bigint PRIMARY KEY CHECK (mlb_id>0),
    pitcher_id bigint NOT NULL UNIQUE CHECK (pitcher_id>0),
    UNIQUE (mlb_id, pitcher_id)
);
CREATE TABLE candidate.public_pitcher_ids (
    export text NOT NULL REFERENCES candidate.public_identity_export(digest),
    mlb_id bigint NOT NULL,
    pitcher_id bigint NOT NULL,
    PRIMARY KEY (export, mlb_id),
    FOREIGN KEY (mlb_id, pitcher_id) REFERENCES candidate.public_pitcher_identity(mlb_id, pitcher_id)
);
GRANT SELECT ON candidate.public_identity_export, candidate.public_pitcher_ids TO sync_v3_worker;

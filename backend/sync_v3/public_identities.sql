CREATE TABLE candidate.public_identity_export (
    singleton boolean NOT NULL DEFAULT true PRIMARY KEY CHECK (singleton),
    digest text UNIQUE NOT NULL CHECK (length(digest)=64),
    payload jsonb NOT NULL
);
CREATE TABLE candidate.public_pitcher_ids (
    export text NOT NULL REFERENCES candidate.public_identity_export(digest),
    mlb_id bigint PRIMARY KEY CHECK (mlb_id>0),
    pitcher_id bigint UNIQUE NOT NULL CHECK (pitcher_id>0)
);
GRANT SELECT ON candidate.public_identity_export, candidate.public_pitcher_ids TO sync_v3_worker;

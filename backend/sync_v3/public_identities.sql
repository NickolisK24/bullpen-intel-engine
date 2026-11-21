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

-- Each generation names the archives that may supply a route. The identity-pair
-- foreign key above guarantees that overlapping exports agree in both directions.
CREATE FUNCTION candidate.edition_identity_archives(generation_digest text)
RETURNS SETOF text LANGUAGE sql STABLE AS $$
    SELECT jsonb_array_elements_text(jsonb_build_array(manifest->'public_identity_export')
                || coalesce(manifest->'earlier_public_identity_exports', '[]'::jsonb))
    FROM candidate.generations WHERE digest=generation_digest AND manifest ? 'public_identity_export'
$$;

CREATE FUNCTION candidate.edition_pitcher_ids(generation_digest text)
RETURNS TABLE (mlb_id bigint, pitcher_id bigint)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT p.mlb_id,p.pitcher_id FROM candidate.edition_identity_archives(generation_digest) AS a(digest)
    JOIN candidate.public_pitcher_ids p ON p.export=a.digest
$$;

-- Only the disposable rehearsal installer creates the reviewer role and this schema.
CREATE TABLE candidate.core_selections (
    revision bigint PRIMARY KEY CHECK (revision > 0),
    predecessor bigint UNIQUE REFERENCES candidate.core_selections(revision),
    action text NOT NULL CHECK (action IN ('select', 'rollback')),
    generation text REFERENCES candidate.generations(digest),
    CHECK ((revision = 1 AND predecessor IS NULL) OR (revision > 1 AND predecessor IS NOT NULL AND predecessor = revision - 1)),
    CHECK (generation IS NOT NULL OR action = 'rollback')
);
GRANT SELECT ON ALL TABLES IN SCHEMA candidate TO sync_v3_reviewer;
GRANT SELECT ON candidate.core_selections TO sync_v3_worker;

-- The reviewer attests to the independent comparison. Neither role can edit an old decision.
CREATE FUNCTION candidate.record_core_selection(expected bigint, target text, operation text)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
    last_entry candidate.core_selections%ROWTYPE;
    old_target text;
    proposed candidate.generations%ROWTYPE;
BEGIN
    IF expected IS NULL OR expected < 0 OR operation IS NULL OR operation NOT IN ('select','rollback') THEN
        RAISE EXCEPTION 'Invalid historical selection request';
    END IF;
    SELECT * INTO last_entry FROM candidate.core_selections ORDER BY revision DESC LIMIT 1;
    IF last_entry.revision = expected + 1 AND last_entry.action = operation
       AND last_entry.generation IS NOT DISTINCT FROM target THEN
        RETURN last_entry.revision;
    END IF;
    IF coalesce(last_entry.revision,0) <> expected THEN
        RAISE EXCEPTION 'Historical selection predecessor changed';
    END IF;
    IF operation='rollback' THEN
        SELECT generation INTO old_target FROM candidate.core_selections WHERE revision=last_entry.predecessor;
        IF last_entry.revision IS NULL OR last_entry.action <> 'select' OR target IS DISTINCT FROM old_target THEN
            RAISE EXCEPTION 'Rollback requires the exact previous selection';
        END IF;
    ELSE
        SELECT * INTO proposed FROM candidate.generations WHERE digest=target;
        IF proposed.digest IS NULL OR target IS NOT DISTINCT FROM last_entry.generation
           OR proposed.manifest->>'contract' IS DISTINCT FROM 'candidate_generation_inventory_v1'
           OR proposed.manifest->'current_serving_eligible' IS DISTINCT FROM 'false'::jsonb
           OR proposed.manifest->'missing' IS DISTINCT FROM '[]'::jsonb
           OR proposed.manifest->'stale_inputs' IS DISTINCT FROM '[]'::jsonb
           OR proposed.manifest->'stale_comparisons' IS DISTINCT FROM '[]'::jsonb
           OR jsonb_array_length(proposed.manifest->'clubs') IS DISTINCT FROM 30
           OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(proposed.manifest->'clubs') c WHERE c->>'readiness'='compared')
           OR EXISTS (SELECT 1 FROM jsonb_array_elements(proposed.manifest->'clubs') c
                      WHERE coalesce(c->>'readiness','') NOT IN ('compared','season_complete'))
           OR proposed.represented < (SELECT represented FROM candidate.generations WHERE digest=last_entry.generation) THEN
            RAISE EXCEPTION 'Ineligible historical selection';
        END IF;
    END IF;
    INSERT INTO candidate.core_selections VALUES (expected+1,last_entry.revision,operation,target);
    RETURN expected+1;
END;
$$;
REVOKE ALL ON FUNCTION candidate.record_core_selection(bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION candidate.record_core_selection(bigint,text,text) TO sync_v3_reviewer;

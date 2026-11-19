"""Retain and replay primary roster inputs using the existing SP source ledger."""

import hashlib
import json

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from models.source_observation import (
    SourceFetchAttempt,
    SourceObservation,
    SourcePayloadArtifact,
    SourceSubject,
)
from services.roster_evidence import (
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
    is_mlb_club,
    roster_entry_player_id,
)
from utils.db import db
from utils.time import to_utc_iso


def _encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _insert_once(model, keys, values):
    # Both dialects enforce the same unique keys. A concurrent insert waits for
    # the first transaction and reuses its row; it never updates immutable data.
    table = model.__table__
    insert = sqlite_insert if db.session.get_bind().dialect.name == "sqlite" else pg_insert
    stmt = insert(table).values(**values).on_conflict_do_nothing(index_elements=keys)
    return db.session.execute(stmt.returning(table.c.id)).scalar_one_or_none()


def _record_view(team_id, kind, day, payload, times, complete, sync_run_id):
    endpoint = f"/teams/{team_id}/roster"
    params = {"rosterType": kind}
    if day:
        params["date"] = day.isoformat()
    request_key = _digest(
        {"version": "request-json-sha256-v1", "schema_version": 1, "parameters": params}
    )
    identity = dict(
        provider="mlb_stats_api",
        source_domain="roster",
        endpoint=endpoint,
        subject_type="team",
        subject_key=f"primary:{team_id}:{kind}",
        request_identity=request_key,
    )
    key = _digest(
        dict(
            identity,
            baseball_date=day.isoformat() if day else None,
            range_start=None,
            range_end=None,
        )
    )
    subject_id = _insert_once(
        SourceSubject,
        ["identity_key"],
        dict(
            identity,
            identity_key=key,
            request_schema_version=1,
            request_parameters=params,
            baseball_date=day,
        ),
    )
    latest = None
    if subject_id is None:
        subject_id = (
            db.session.query(SourceSubject.id)
            .filter_by(identity_key=key)
            .with_for_update()
            .scalar()
        )
        latest = (
            SourceObservation.query.filter_by(source_subject_id=subject_id)
            .order_by(SourceObservation.version_number.desc())
            .first()
        )
    digest = _digest(payload)
    completeness = "complete" if complete else "partial"
    count = len(payload["records"])
    started, completed = times
    if latest and latest.fingerprint == digest and latest.completeness == completeness:
        observation = latest
        outcome = "unchanged" if complete else "partial"
    else:
        artifact_key = dict(
            content_hash=digest, payload_schema_version=1, payload_kind="normalized_json"
        )
        artifact_id = _insert_once(
            SourcePayloadArtifact,
            list(artifact_key),
            dict(
                artifact_key,
                hash_algorithm="sha256",
                storage_format="json",
                payload_json=payload,
                payload_bytes=len(_encoded(payload)),
            ),
        )
        if artifact_id is None:
            artifact_id = (
                db.session.query(SourcePayloadArtifact.id).filter_by(**artifact_key).scalar()
            )
        if not complete:
            outcome = "partial"
        elif not count:
            outcome = "empty_valid"
        else:
            outcome = "changed" if latest else "new"
        version = latest.version_number + 1 if latest else 1
        observation = SourceObservation(
            source_subject_id=subject_id,
            version_number=version,
            dedupe_key=_digest([key, version, digest]),
            fingerprint=digest,
            fingerprint_algorithm="sha256",
            fingerprint_version="source-json-sha256-v1",
            payload_artifact_id=artifact_id,
            payload_schema_version=1,
            completeness=completeness,
            outcome=outcome,
            is_change=complete,
            is_authoritative=complete,
            record_count=count,
            predecessor_observation_id=latest.id if latest else None,
            observed_at=completed,
            sync_run_id=sync_run_id,
        )
        db.session.add(observation)
        db.session.flush()
    db.session.add(
        SourceFetchAttempt(
            source_subject_id=subject_id,
            source_observation_id=observation.id,
            sync_run_id=sync_run_id,
            started_at=started,
            completed_at=completed,
            completeness=completeness,
            outcome=outcome,
            status="succeeded" if complete else "partial",
            record_count=count,
        )
    )
    return observation.id


def retain_roster_inputs(evidence, team_id, sync_run_id, errors):
    """Attach the two membership inputs and retain the context for false versus unknown."""
    observations = {}
    partial = {error["roster_type"] for error in errors}
    for kind in (ROSTER_TYPE_FULL, ROSTER_TYPE_NON_ROSTER, ROSTER_TYPE_40_MAN, ROSTER_TYPE_ACTIVE):
        view = evidence.roster_view(team_id, kind)
        if view.error:
            raise ValueError("Cannot retain a failed roster fetch as a membership input")
        records = list(view.entries)
        payload = {"records": records, "roster_sha256": _digest(records)}
        if kind == ROSTER_TYPE_ACTIVE:
            payload["companion_observations"] = dict(observations)
            # The snapshot identifies this exact acquisition even for identical
            # rosters fetched twice in a run, or for a writer without a run ID.
            payload["acquired_at_utc"] = {
                roster_type: to_utc_iso(evidence.fetch_times[team_id, roster_type][1])
                for roster_type in (*observations, ROSTER_TYPE_ACTIVE)
            }
        observations[kind] = _record_view(
            team_id,
            kind,
            evidence.represented_date,
            payload,
            evidence.fetch_times[team_id, kind],
            kind not in partial,
            sync_run_id,
        )
    return dict(
        active_roster_observation_id=observations[ROSTER_TYPE_ACTIVE],
        forty_man_roster_observation_id=observations[ROSTER_TYPE_40_MAN],
    )


def replay_membership(snapshot):
    """Recompute the two nullable flags offline. Unlinked, partial or inconsistent evidence refuses."""
    observed = {}
    ids = {ROSTER_TYPE_ACTIVE: snapshot.active_roster_observation_id}
    for kind in (ROSTER_TYPE_ACTIVE, ROSTER_TYPE_40_MAN, ROSTER_TYPE_FULL, ROSTER_TYPE_NON_ROSTER):
        obs = db.session.get(SourceObservation, ids[kind]) if ids.get(kind) else None
        if (
            not obs
            or not obs.is_authoritative
            or obs.completeness != "complete"
            or not obs.payload_artifact
        ):
            raise ValueError(f"Missing or incomplete primary roster input: {kind}")
        subject = obs.subject
        params = {"rosterType": kind}
        if subject.baseball_date:
            params["date"] = snapshot.snapshot_date.isoformat()
        if (
            subject.subject_key != f"primary:{snapshot.team_id}:{kind}"
            or subject.request_parameters != params
            or subject.endpoint != f"/teams/{snapshot.team_id}/roster"
            or (
                subject.baseball_date is not None
                and subject.baseball_date != snapshot.snapshot_date
            )
            or subject.source_domain != "roster"
            or subject.provider != "mlb_stats_api"
        ):
            raise ValueError(f"Roster request scope mismatch: {kind}")
        artifact = obs.payload_artifact
        payload = artifact.payload_json
        if (
            _digest(payload) != artifact.content_hash
            or _digest(payload["records"]) != payload.get("roster_sha256")
            or obs.fingerprint != artifact.content_hash
            or len(payload["records"]) != obs.record_count
        ):
            raise ValueError(f"Roster digest or count mismatch: {kind}")
        if kind == ROSTER_TYPE_ACTIVE:
            ids.update(payload["companion_observations"])
            if ids.get(ROSTER_TYPE_40_MAN) != snapshot.forty_man_roster_observation_id:
                raise ValueError("Mismatched active and forty-man roster inputs")
        observed[kind] = any(
            roster_entry_player_id(row) == snapshot.mlb_id for row in payload["records"]
        )
    if not any(observed.values()):
        return None, None
    if not is_mlb_club(snapshot.team_id):
        return False, False
    return observed[ROSTER_TYPE_ACTIVE], observed[ROSTER_TYPE_40_MAN]

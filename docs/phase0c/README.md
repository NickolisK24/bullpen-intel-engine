# Phase 0C - Reliever Appearance Evidence Layer

Phase 0C stores source facts for reliever appearance evidence. It does not add
public evidence interpretation, prediction, manager-intent language, betting
framing, pressure scores, role inference, or pitch-level ingestion.

## Product Rule

- Use as much relevant baseball data as possible.
- Interpret it through a bullpen lens.
- Show the evidence clearly.
- Avoid unsupported claims.

## Current Branch

Branch 0C-05 adds the transaction and IL foundation as typed source facts with
roster-snapshot alignment. Transactions explain later context only; they do not
decide current roster state or create public evidence reads in Phase 0C.

## Required Ingestion Contract

Every future Phase 0C ingestion/storage branch must document and test:

- Final-only source gate before public evidence can rely on completed-game data.
- Unknown-safe nullable storage for values that may be absent or unsafe.
- No zero defaults for unknown stat values.
- Source provenance fields or an explicit adapter to existing provenance fields.
- Correction-policy registration for every correction-sensitive field/table.
- Source-readiness family registration before consumers treat data as usable.
- Dead-letter behavior for source fetch, shape, identity, or correction failure.
- Fail-closed handling for unavailable, stale, degraded, never-fetched, or
  unknown readiness.
- Tests for finality gates, unknown handling, provenance, correction policy,
  readiness, and no public display in Phase 0C.

## Guardrails

- No public display in Phase 0C.
- No raw response cache unless legal and storage posture is cleared.
- No live or in-progress feed for public evidence.
- No health claims from missing IL or injury flags.
- No prediction, betting, manager-intent, confidence-score, fatigue-score, or
  score framing.
- No source family should be marked ready before it exists and has provenance.
- Missing provenance means the family is not ready.
- Transactions and IL facts must not persist raw responses, free-text injury
  descriptions, health claims, return timetables, depth-pressure reads, or
  availability labels.

## Branch Map

- 0C-01: finality/status hardening
- 0C-02: source readiness and provenance framework
- 0C-03: boxscore field expansion
- 0C-04: roster status snapshots
- 0C-05: transactions and IL foundation
- 0C-06: final play-by-play foundation
- 0C-07: starter exposure and calendar foundation
- 0C-08: source coverage integration and exit

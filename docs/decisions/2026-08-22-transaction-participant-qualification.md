# Transaction Participant Qualification

Date: 2026-08-22
Status: Accepted

## Decision

Recent Transactions may exclude a team-touching source row from bullpen
chronology completeness only when explicit MLB position evidence proves the
participant is a non-pitcher. The governed internal states are `pitcher`,
`non_pitcher`, and `unresolved`.

Canonical `Pitcher` identity proves pitcher relevance. For participants without
that linkage, transaction ingestion reads MLB person `primaryPosition`
authority. Code `1`, abbreviation `P`, or type `Pitcher` proves pitcher.
Two-way evidence remains pitcher-relevant. This includes code `Y`, abbreviation
`TWP`, or an explicit two-way type. Any other explicit position proves
non-pitcher. Missing or unusable position evidence remains unresolved.

Absence of a canonical `Pitcher` row never proves non-pitcher status.

## Writer and query boundary

The daily transaction writer deduplicates the MLB person IDs that lack a
canonical Pitcher and performs at most one deduplicated batch `/people` request.
It persists only the typed qualification, exact authority, and source position
fields on `PlayerTransaction`. Source position carried directly on a structured
transaction row may satisfy the same rule without a people lookup.

The public Team Board reader performs no network call and adds no query. It
revalidates persisted non-pitcher evidence against the canonical authority and
position rule before excluding a row from completeness accounting. Missing,
malformed, mismatched, or wrongly stamped evidence fails closed.

## Completeness interaction

A proven non-pitcher is irrelevant to bullpen chronology and neither renders nor
contributes a withheld-row limitation. A proven pitcher still must satisfy the
existing canonical Pitcher linkage, event taxonomy, historical team, and roster
alignment rules before rendering. An unresolved role remains potentially
pitcher-relevant and continues to make that team's chronology partial.

The public response contract does not change. No classification counts, source
position codes, or debug evidence are exposed.

## Historical integrity

Qualification is evidence about bullpen relevance only. Transaction date and
`from_team_id` and `to_team_id` remain unchanged and continue to own chronology
and historical team attribution. Current team assignment cannot rewrite an
event. Repeated natural transaction syncs may correct persisted role evidence
under the existing source-correction policy; no historical backfill or
request-time reconstruction is authorized.

## Scope

This decision does not change transaction event taxonomy, Roster Context,
Off-Active Count, active bullpen membership, Team State, Rest Status, workload,
Rotation Impact, Performance, Recent Relief Work, or frontend presentation.

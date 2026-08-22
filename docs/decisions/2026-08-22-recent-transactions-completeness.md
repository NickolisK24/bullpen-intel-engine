# Recent Transactions Completeness

Date: 2026-08-22
Status: Accepted with a remaining source-authority gap

## Decision

Recent Transactions remains a reader-safe chronology of verified pitcher
movement, distinct from current Roster Context. The existing core row authority
is sound, but the public chronology cannot claim complete coverage while a
team-touching source row lacks canonical pitcher identity, a governed event
category, or verified transaction-time team alignment.

Partial remains the correct public state in that case.

## Window and currentness

Transaction ingestion owns a bounded source interval `[D-7, D]`, inclusive,
using official transaction date rather than ingestion time. The public reader
uses the latest successful or partial source window and restricts it through the
represented Team Board date. A source row later than that represented date is
not public for that board. If the represented date predates the source window,
the chronology is unavailable rather than reconstructed from older data.

Rows are ordered by transaction date descending, then stable transaction key
and stored row identity ascending. A successful authoritative window with no
qualifying rows is a valid empty chronology.

## Public row authority

A public row requires all of:

- a stored `PlayerTransaction` linked to a canonical `Pitcher` identity;
- a supported structured `normalized_category` with backend-owned label and
  description;
- transaction-time team authority in `from_team_id` or `to_team_id`;
- roster-snapshot alignment already marked explanatory-eligible by ingestion;
- an event date inside the represented public window.

The source transaction ID owns identity when present. Otherwise the canonical
fallback key hashes the player, dates, structured type, transaction teams, and
retroactive date. The database uniqueness constraint and ingestion upsert make
repeat observations idempotent. No frontend deduplication or classification is
authorized.

## Historical team ownership

Historical event selection reads immutable transaction-side `from_team_id` and `to_team_id`.
Mutable current pitcher assignment has no role in transaction
ownership. A traded, released, optioned, recalled, injured-list, or activated
player remains attached to the teams carried by the source event. Missing or
conflicting alignment fails closed for that row.

## Availability boundary

- **Available:** the source window is current, the represented date is covered,
  and no material source or team-touching row is withheld.
- **Partial:** verified rows may be shown, but the source window contains an
  unscoped failure or a selected team-touching row cannot satisfy the public row
  authority. Unknown player identity, event type, or team alignment is not
  assumed to be irrelevant position-player traffic.
- **Unavailable:** no usable source window exists, the latest attempt failed,
  the source is stale, or the represented date is outside its coverage.

The live audit on 2026-08-22 found verified rows and withheld team-touching rows
across the current MLB Team Board reads. That is a real source-authority gap,
not explanatory copy accidentally promoted into runtime limitations. The
reader must not promote those teams to Available until the missing authority is
actually resolved.

## Roster Context independence

Roster Context remains independently governed by `roster_authority_v1`.
Its current reference date controls that read. Transaction chronology does not reconstruct the roster,
and current roster state does not rewrite historical events. A partial or
unavailable chronology therefore does not invalidate Off-Active Count, active
bullpen membership, or named current roster-status evidence.

## Unsupported cases

The reader continues to withhold unknown structured transaction categories,
unlinked player identities, missing transaction teams, and roster-snapshot
alignment failures. It does not fetch player positions on demand, guess from
free text, backfill history, or add per-player queries. A future source-authority
package may distinguish proven non-pitcher source traffic from unresolved
pitcher movement; this decision does not create that authority.

## Scope

This change only aligns chronology with the represented Team Board date and
records the existing fail-closed completeness boundary. It does not change
transaction ingestion, roster classification, Off-Active Count, active bullpen
membership, Team State, Rest Status, workload, Performance, Rotation Impact,
Recent Relief Work, What Changed, or frontend presentation.

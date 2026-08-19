# Versioned daily delta substrate

Status: approved for TB-09A prospective infrastructure only.

Team Board daily comparison must fail closed unless two frozen reads prove
semantic compatibility. Existing dashboard history cannot provide that proof:
its prior-date values were frozen, but Team State method and population
authority were not stamped for comparison.

TB-09A therefore records one append-only `team_board_delta` sidecar in the
existing dashboard snapshot store when, and only when, a new immutable Team
State Share Artifact is published. The sidecar freezes the represented baseball
date, source artifact/snapshot/sync identities, canonical Team State method and
contract versions, population-authority identity, trust eligibility, and the
raw governed Team State value. Reused artifacts do not create a sidecar, so old
history remains unstamped and incomparable. No backfill or historical
recomputation is authorized.

The sole protected orchestration path authorized for this capture is
`backend/services/share_artifact_generation.py`. It may pass the readiness and
artifact values already in its publication transaction to the append-only
sidecar writer. No Share Artifact payload or historical row is modified. No
Team State classifier, threshold, vocabulary, eligibility, artifact integrity,
public serving contract, or existing `/changes` behavior changes.

The comparison service may return raw previous/current values only for domains
whose method, contract, population, source identity, trust, and represented-date
requirements match. Missing or incompatible metadata is a typed withheld
result. What Changed presentation and prose remain outside TB-09A.

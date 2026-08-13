# Depth Safety Reconciliation

Targeted reconciliation of the one read the observation audit flagged as the
most misleading false positive: **Depth Safety**. The read was internally
consistent but could describe bullpen *size* as bullpen *strength* — a weak,
high-pressure pen could still earn "Strong Depth Safety" purely on reliever
volume. This branch adds a single trust-anchor guardrail so deep volume only
reads Strong when there is a usable primary corps to fall back from. One read
changed; the public labels are unchanged.

## What Depth Safety should answer

> If the primary bullpen arms become unavailable, how much fallback support
> exists?

Not "how many relievers exist?" Fallback only means something behind a usable
primary corps. A bullpen with no usable Trust Arm has no anchored late-inning
option — its Depth Arms are already the front line, not a reserve.

## Audit — current behavior

The prior logic was pure volume:

- Strong — `total ≥ 8` and `≥ 3` Depth Arms and `≥ 2` available Depth Arms.
- Stable — `total ≥ 7` and `≥ 2` Depth Arms and `≥ 1` available.
- Thin — `≥ 1` Depth Arm available.
- Limited — otherwise.

Run through the observation harness (`scripts/bullpenShapeObservation.mjs`):

**False positives (size read as strength):**
- *Weak A (Rockies archetype)* — 8 arms, 5 Depth Arms, trust restricted, **High
  Bullpen Pressure** — read **Strong Depth Safety**. High Pressure and Strong
  Depth on the same pen.
- *Interesting B (depth-rich, trust gassed)* — 8 arms, 5 clean Depth, both Trust
  Arms restricted, **High Pressure** — read **Strong Depth Safety**.

**Legitimate positives (kept):**
- *Strong A (Dodgers archetype)* — deep, two clean Trust Arms anchoring — **Strong**.
- *Strong B / balanced pens* — **Stable**, correctly.

**Edge cases (pressure and depth point opposite):** exactly the two false
positives above — the read pointed "strong" while Pressure pointed "high." That
opposition is the signal this branch reconciles.

## Investigation findings

1. **Volume vs meaningful depth** — confirmed. The read keyed entirely off arm
   counts; nothing distinguished "seven bodies" from "usable fallback."
2. **Trust Availability interaction** — Depth Safety should *not* be fully
   isolated. When no usable Trust Arm exists, depth is not fallback, so "Strong"
   overstates. This is the guardrail implemented.
3. **Clean Options interaction** — no duplication introduced. Clean Options
   weights clean arms by role to size meaningful clean inventory; Depth Safety
   still answers a different question (fallback behind the primary corps). The
   guardrail reuses only the usable-trust signal, not Clean Options' logic.
4. **Role weighting** — Depth Safety stays depth-described. Trust Arm influence
   never inflates the depth count; it only gates the top tier. A trust-rich but
   depth-thin pen still cannot reach Strong (verified by test).

## Logic change

A single guardrail on the Strong tier:

- Strong — deep volume **and** at least one usable Trust Arm (clean or watch)
  anchoring the bullpen.
- If the volume qualifies for Strong but no usable Trust Arm exists, the read is
  **Stable** instead, with an explanation: "No usable Trust Arm anchors the
  bullpen, so this depth reads Stable rather than Strong — fallback volume
  without a primary corps in front of it."
- Stable / Thin / Limited / Limited Read tiers are unchanged.

The read is never lowered below Stable by the guardrail — the bullpen genuinely
has depth bodies, so it is not punished into looking empty. The guardrail only
withholds the top "Strong" claim from pens with no anchor.

## Before vs after

Labels from the live engine via the observation harness.

| Bullpen | Pressure | Before | After | Why |
| --- | --- | --- | --- | --- |
| Weak A — 5 Depth, trust restricted | High | Strong | **Stable** | No usable Trust Arm to anchor the depth. |
| Interesting B — 5 clean Depth, trust gassed | High | Strong | **Stable** | Same — deep bodies, no primary corps. |
| Strong A — deep, 2 clean Trust | Low | Strong | Strong | Anchored; legitimately deep. |
| Strong B / balanced | Low | Stable | Stable | Unchanged. |
| Interesting A — trust-rich, depth-thin | Elevated | Limited | Limited | Trust never inflates depth. |
| Sparse | — | Limited Read | Limited Read | Unchanged gate. |

The two High-Pressure pens no longer pair with "Strong Depth Safety"; every
legitimately deep, anchored pen keeps it.

## Validation scenarios

- **A — many Depth, no usable Trust, High Pressure:** not Strong (Stable). ✓
- **B — many Depth, healthy Trust group:** Strong justified. ✓
- **C — small bullpen, strong Trust core:** depth stays Thin/Limited. ✓
- **D — balanced bullpen:** Stable. ✓
- **E — sparse data:** Limited Read. ✓

## Explainability

The read carries `usableTrustArms` and an `anchoredByTrust` flag in
`supportingCounts`, and a capped read states plainly why it is only Stable. A
user can see that a deep bullpen reads Stable because no trusted arm anchors it —
no hidden math, no weight value, score, or band exposed.

## Scope and constraints

- Changed only `depthSafety` in `frontend/src/utils/teamBullpenScoring.js`.
- Bullpen Pressure, Clean Options, Trust Arm Availability, and Coverage Safety
  are untouched (verified by their existing tests and a cross-read test).
- No backend, schema, sync, availability/fatigue engine, or page-structure
  changes. Public labels and concept vocabulary preserved.

## Recommendation — was Depth Safety truly flawed, or merely misunderstood?

**Both, narrowly.** The read was not broken — it correctly measured what it
measured (available depth volume) and was internally consistent. It was
*misframed*: presented as a safety/strength read while actually answering a
volume question, so on weak pens it implied strength the bullpen did not have.
The fix is not a rewrite but a guardrail that restores the intended meaning —
fallback behind a usable primary corps. With this, Depth Safety now describes
meaningful depth rather than raw volume, and the last major reconciliation gap
the observation audit identified is closed. Health-ranking readiness should be
re-assessed only after this and a live-data validation pass, not before.

# Probe Protocol

Phase 0B probes are read-only research artifacts. Branch 0B-01 does not add or
run probes; this protocol defines rules for later audit branches if probes are
needed.

## Read-Only Probe Rules

- Probe scripts, if later added, must live only under a clearly marked
  non-production research path.
- Probe scripts must never be imported by app or sync code.
- Probe scripts must never be scheduled.
- Probe scripts must never write to the production database.
- Probe records must be stored beside the relevant audit doc.
- Probe evidence must be reproducible.
- Probe evidence must distinguish observed facts from interpretation.

## Required Probe Record

Every probe must record:

- date
- endpoint/source
- request parameters
- response excerpt
- observed field behavior
- finality/correction notes
- failure/empty/partial behavior

## Evidence Standard

Probe records should separate:

- observed facts: what endpoint/source was requested, what parameters were
  used, what response excerpt was returned, and what field behavior was seen;
- interpretation: what the observed behavior may mean for BaseballOS source
  classification, finality safety, correction behavior, failure modes,
  storage risk, and public-display posture.

Probe records cannot replace legal review. Any legal conclusion must cite
source terms or remain marked `needs-legal-review`.

# Phase 0D Language Rules

## Purpose

Evidence claims must describe cited stored facts without implying certainty that
the source foundation does not support. These rules apply to claim templates and
rendered claims before any evidence object can be stored.

## Safe Language

Safe language is citation-first and limited to what the registered rule defines.

- Descriptive facts: "recorded", "stored", "listed", "appeared", "entered",
  "exited", "used", "flagged", "not flagged", "unknown", "withheld".
- Defined labels with visible definitions: labels are allowed only when the rule
  definition names the label, required inputs, and completeness behavior.
- No public IL flag phrasing: "No public IL flag is stored for this pitcher in
  the cited roster snapshot." This is not a health claim.
- Usage-observation phrasing: "The cited game log records 18 pitches."
- Citation-first claim language: "Based on the cited final game log..."
- Unknown wording: "Evidence unknown because the required cited input is null."
- Withheld wording: "Evidence withheld because the required source family is not
  ready."
- Conflict wording: "Evidence conflict because cited rows disagree."

## Forbidden Language

Claim templates and rendered claims must not use:

- betting language
- odds language
- projection language
- prediction framing, including "will", "should", "expect", and "likely" when
  used as prediction or availability certainty
- manager-intent certainty, including "trusts", "prefers", "won't use", or
  similar language
- unsupported health language, including "healthy", "injury-free", "full
  strength", or "nobody is hurt"
- public fatigue, confidence, trust, or pressure scores
- score, grade, rank, or color-state framing
- official role-title assertions as claims, including "closer", "setup man",
  or "fireman", unless a later branch explicitly allows sourced official
  metadata

## Lint Behavior

Registration or rendering fails when a claim template or rendered claim matches
a forbidden-language rule. The lint is intentionally conservative in 0D-01.
Later branches may add narrower allowlists only when a rule definition,
citations, and tests prove the wording is safe.

## Unknown, Withheld, And Conflict Wording

Non-complete evidence must not pretend to be a confident claim.

- Unknown: name the missing cited input.
- Withheld: name the source posture or readiness reason.
- Conflict: cite both sides and preserve the contradiction.

No branch may turn null into zero, hide contradictory rows, or convert source
absence into a public health or availability claim.

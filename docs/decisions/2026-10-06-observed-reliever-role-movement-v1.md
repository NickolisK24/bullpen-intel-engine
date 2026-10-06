# Observed Reliever Role Movement Authority V1

**Date:** 2026-10-06  
**Package:** ML-01  
**Status:** Candidate authority on protected branch; production cutover not authorized.

## Decision

BaseballOS may describe a reliever's observed deployment movement by comparing
two adjacent seven-calendar-day windows when both windows contain enough
comparable completed relief appearances.

This is a descriptive deployment read. It does not identify a bullpen job,
predict the next appearance, infer manager intent, predict availability, or
claim pitcher quality.

## Source authority

- Population: official team-at-appearance relief appearances.
- Historical team: `GameLog.appearance_team_id`; current roster membership
  never rewrites a prior appearance.
- Starter exclusion: `games_started == 0`.
- Included MLB game types: regular season `R`, Wild Card `F`, Division
  Series `D`, League Championship Series `L`, and World Series `W`.
- Entry evidence: fully processed play-by-play only.
- Leverage evidence: recorded appearance-level leverage index only. Save, hold,
  inning, score, or role label never substitutes for missing leverage.
- Recent window: `[D-6, D]`.
- Prior window: `[D-13, D-7]`.

## Minimum evidence

Each window requires at least three official relief appearances. Entry-inning and
recorded-leverage signals are independently comparable. A missing signal is
withheld rather than converted to zero.

A public movement may be authored when at least one signal is comparable and
the comparable signals do not disagree directionally.

## Movement semantics

V1 uses two descriptive shares:

1. appearances entering in the eighth inning or later;
2. appearances with recorded leverage index at or above the existing public
   high-leverage boundary.

A share shift of at least 0.50 is material for this first bounded contract.

Public outcomes are:

- `later_or_higher_leverage`: recent completed deployment shifted toward
  later or higher-leverage work;
- `earlier_or_lower_leverage`: recent completed deployment shifted toward
  earlier or lower-leverage work;
- `stable`: comparable deployment did not cross the movement boundary.

Mixed directional evidence is unavailable, not averaged into a conclusion.

## Publication and reader boundary

The classifier runs at publication time. Its result is frozen into the trusted
Team Board deployment carrier. Public requests do not recalculate movement.

The frontend may render the backend-authored public sentence and factual window
counts. It may not calculate shares, thresholds, direction, materiality, role
titles, or future usage.

Older immutable publications are not rewritten. A publication without this
carrier remains valid and simply has no role-movement read.

## Explicitly not authorized

- closer/setup/fireman promotion or demotion claims;
- manager-intent language;
- future deployment or save-opportunity prediction;
- health/readiness inference;
- rankings, grades, scores, or recommendations;
- historical replay/backfill;
- What Changed events;
- Team State or Arm Read input;
- production merge or deployment solely because this document exists.

## Production gate

ML-01 remains branch-only until backend, frontend, browser, dependency,
migration, freeze/contract, and publication tests pass and the draft PR is
reviewed for production cutover.

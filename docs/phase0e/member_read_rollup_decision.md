# Phase 0E Member-Read Rollup Decision

## Ruling

MEMBER-READ ROLLUP (ratified): REJECT-AND-CLOSE, recorded as
CLOSED-UNLESS-REOPENED with named preconditions.

## Closure

The composed-read contract remains component-to-evidence only. Components cite
stored evidence objects through `composed_read_evidence_citations`. No component
cites another composed read. No read-citation table, read foreign key, or
`allowed_read_types` registry support is added in 0E-05.

## Reopening Preconditions

This decision may be reopened only if all named preconditions exist:

- specific product display need;
- read-citation contract extension;
- migration;
- `allowed_read_types` support;
- read-to-read recompute;
- separate review.

Until then, member-read rollup remains closed.

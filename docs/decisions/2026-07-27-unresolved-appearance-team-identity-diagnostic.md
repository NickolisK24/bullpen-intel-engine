# Unresolved appearance-team identity diagnostic

## Decision

The first governed dry run for GameLog `41040` failed closed because the target pitcher's stored MLB id was not present in the official box-score pitching lines for game `824262`.

Before changing any identity or attribution contract, BaseballOS will run a private, read-only diagnostic that reports the stored pitcher identity, official game teams, a bounded list of official pitching identities, and exact pitching-stat matches. The diagnostic never uses current team assignment, never chooses a replacement identity, and never writes database data.

A statistical match is diagnostic evidence only. It cannot authorize the repair by itself. Any later correction must establish the pitcher's official identity and represented team through a separately reviewed, fail-closed contract.

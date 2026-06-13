// The BaseballOS language layer — where internal bullpen signals get
// translated into the words a baseball person would actually say.
//
// Layering (see docs/product/LANGUAGE_ENGINE_V1.md for the full spec):
//
//   internal reads                       language layer        user-facing story
//   (bullpenConcepts, teamBullpenScoring,  →  this module  →   (homepage, stories
//    landscape counts, board counts)                            feed, team panels)
//
// The ontology itself is untouched: Recovery Window, Workload Concentration,
// Bullpen Pressure, Clean Options, Coverage Safety, and Depth Safety keep
// their names and keep riding every surface as evidence — read chips, stat
// labels, the Today's Bullpen Shape strip. This module only owns how those
// signals sound when they become a sentence. Two rules govern everything in
// it: concepts never act as the subject of a sentence ("Workload
// Concentration stacks up" is model voice; "heavy use on the same arms
// stacks up" is baseball), and prose never uses system verbs ("register as",
// "carrying a signal").
//
// Each signal maps to a small pool of headline builders keyed by the slot
// that uses it, so a signal sounds like itself everywhere without repeating
// one sentence verbatim across surfaces. Alternates considered for each pool
// live in the spec doc. Everything stays descriptive and present-tense —
// no forecasts, no verdicts, no advice.

export const SIGNAL_HEADLINES = {
  // ── Bullpen Pressure / narrow Recovery Window ─────────────────────────────
  // Internal: the pen is short on rested arms after recent workload.
  // Says: stretched thin, a short bench, less margin than most.
  stretchedPen: {
    hero: (team) => `The ${team} bullpen is stretched thinner than any in baseball today`,
    feed: (team) => `A thin late-inning margin is forming for the ${team}`,
    team: (team) => `The ${team} enter today with a thin late-inning margin`,
  },

  // ── Workload Concentration ────────────────────────────────────────────────
  // Internal: recent work is clustered on a few arms instead of spread out.
  // Says: leaning on the same arms, the same names every night, heavy work
  // falling on a small group.
  sameArms: {
    hero: (team) => `The ${team} are leaning on the same arms more than anyone in baseball today`,
    feed: (team) => `The ${team} keep handing the ball to the same relievers`,
    hidden: (team) => `The ${team} box score looks calm. The bullpen does not.`,
    team: (team) => `The ${team} look calm on the surface — the workload underneath is worth watching`,
  },

  // ── Wide Recovery Window / deep Clean Options ─────────────────────────────
  // Internal: most of the pen comes in rested, with no workload restriction.
  // Says: bullpen flexibility, room to maneuver, rested options.
  freshPen: {
    hero: (team) => `The ${team} have more bullpen flexibility than anyone in baseball today`,
    feed: (team) => `No club has more late-inning options today than the ${team}`,
    depth: (team) => `The ${team} have rested options behind the late innings today`,
    team: (team) => `The ${team} have one of baseball's deeper bullpens available today`,
  },
}

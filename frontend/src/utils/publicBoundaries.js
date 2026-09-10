// The canonical public boundary language for BaseballOS.
//
// About, How to Read, and Methodology all describe the same product limits.
// Those statements live here once — pages render from this module instead of
// keeping their own slightly different copies, so the boundary language can
// never drift between surfaces.
//
// These are product boundaries, not glossary entries; the public dictionary
// of named reads and labels lives in utils/bullpenConcepts.js.

export const PUBLIC_BOUNDARIES = Object.freeze({
  // What the product is.
  descriptiveScope:
    'BaseballOS describes bullpen context. It does not predict outcomes, rank pitchers, or tell you who to use.',

  // The "does not do" set.
  noPicks: 'No picks. It never tells you who to use or who to bet.',
  noPredictions: "No predictions. It describes today's context, not tomorrow's outcome.",
  noBettingAdvice: 'No betting advice. It is not a wagering or odds product.',
  noPrivateInjuryClaims: 'No private injury claims. The absence of a public flag is not a health claim.',
  noManagerCertainty:
    'No certainty about manager decisions. It cannot see bullpen phones, intent, or final game-day calls.',

  // What the data cannot contain.
  unknowns:
    'Manager intent, bullpen phone activity, private medical availability, and final game-day decisions are not known to BaseballOS.',
  notHealthClaim: 'The absence of a public flag is not a health claim.',

  // How the product behaves when a read is uncertain.
  saysSoInsteadOfGuessing:
    'When a read cannot be made with confidence, BaseballOS says so instead of guessing.',
})

// The ordered "What BaseballOS does not do" list rendered on About.
export const PUBLIC_BOUNDARY_LIST = Object.freeze([
  PUBLIC_BOUNDARIES.noPicks,
  PUBLIC_BOUNDARIES.noPredictions,
  PUBLIC_BOUNDARIES.noBettingAdvice,
  PUBLIC_BOUNDARIES.noPrivateInjuryClaims,
  PUBLIC_BOUNDARIES.noManagerCertainty,
])

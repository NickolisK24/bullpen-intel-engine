// Concept marks for the BaseballOS vocabulary.
//
// Each glyph is an abstract line drawing of the idea behind a named concept —
// a recovery arc, compressed workload lines, branching clean routes, a covered
// late-inning path, a group of known arms, clustered versus distributed work.
// They exist to make the vocabulary recognizable as BaseballOS language, not to
// measure anything.
//
// Deliberate constraints:
//   - no value, tier, percentage, ring, gauge, meter, or star is representable
//     here; every path is fixed geometry with no data input;
//   - hand-authored inline SVG, so no icon library and no bundle weight beyond
//     the markup itself;
//   - decorative, so every glyph is aria-hidden and the concept name always
//     carries the meaning as text;
//   - `currentColor` throughout, so a glyph inherits whatever restraint the
//     surrounding text already has.

const SHARED = {
  viewBox: '0 0 40 40',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.4,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

// Recovery Window — an arc reopening over a rest baseline.
function RecoveryGlyph() {
  return (
    <>
      <path d="M4 30h32" strokeOpacity="0.3" />
      <path d="M6 30a14 14 0 0 1 28 0" />
      <path d="M20 30V16" strokeOpacity="0.45" />
      <circle cx="20" cy="30" r="1.6" fill="currentColor" stroke="none" />
    </>
  )
}

// Bullpen Pressure — stacked workload lines compressing toward one point.
function PressureGlyph() {
  return (
    <>
      <path d="M5 11h30" strokeOpacity="0.3" />
      <path d="M8 17h24" strokeOpacity="0.5" />
      <path d="M11 23h18" strokeOpacity="0.75" />
      <path d="M14 29h12" />
    </>
  )
}

// Workload Concentration — work clustered on a few arms rather than spread.
function ConcentrationGlyph() {
  return (
    <>
      <circle cx="9" cy="12" r="1.6" strokeOpacity="0.4" />
      <circle cx="9" cy="28" r="1.6" strokeOpacity="0.4" />
      <circle cx="27" cy="18" r="2.6" fill="currentColor" stroke="none" />
      <circle cx="32" cy="24" r="2.2" fill="currentColor" stroke="none" />
      <circle cx="24" cy="26" r="1.8" fill="currentColor" stroke="none" />
      <path d="M13 14l9 3M13 26l8 1" strokeOpacity="0.4" />
    </>
  )
}

// Clean Options — routes branching away from a single entry point.
function CleanOptionsGlyph() {
  return (
    <>
      <path d="M4 20h10" />
      <path d="M14 20c8 0 8-10 16-10" />
      <path d="M14 20h22" strokeOpacity="0.7" />
      <path d="M14 20c8 0 8 10 16 10" strokeOpacity="0.45" />
      <circle cx="14" cy="20" r="2" fill="currentColor" stroke="none" />
      <circle cx="34" cy="10" r="1.6" strokeOpacity="0.7" />
      <circle cx="34" cy="30" r="1.6" strokeOpacity="0.45" />
    </>
  )
}

// Coverage Safety — a late path held under two spans of cover.
function CoverageGlyph() {
  return (
    <>
      <path d="M4 12a16 16 0 0 1 32 0" />
      <path d="M11 20a9 9 0 0 1 18 0" strokeOpacity="0.5" />
      <path d="M6 31h28" strokeOpacity="0.35" />
      <path d="M20 31v-5" strokeOpacity="0.5" />
      <circle cx="20" cy="31" r="1.8" fill="currentColor" stroke="none" />
    </>
  )
}

// Trusted Arms — a group of known nodes on one connected path.
function TrustedArmsGlyph() {
  return (
    <>
      <path d="M6 25c6 0 6-10 14-10s8 10 14 10" strokeOpacity="0.45" />
      <circle cx="10" cy="21" r="2.4" />
      <circle cx="20" cy="15" r="2.4" fill="currentColor" stroke="none" />
      <circle cx="30" cy="21" r="2.4" />
    </>
  )
}

const GLYPHS = {
  recovery: RecoveryGlyph,
  pressure: PressureGlyph,
  concentration: ConcentrationGlyph,
  cleanOptions: CleanOptionsGlyph,
  coverageSafety: CoverageGlyph,
  trustedArms: TrustedArmsGlyph,
}

export default function ConceptGlyph({ name, className = '' }) {
  const Glyph = GLYPHS[name]
  if (!Glyph) return null
  return (
    <svg
      {...SHARED}
      aria-hidden="true"
      focusable="false"
      className={`h-12 w-12 shrink-0 ${className}`}
    >
      <Glyph />
    </svg>
  )
}

export const CONCEPT_GLYPH_KEYS = Object.freeze(Object.keys(GLYPHS))

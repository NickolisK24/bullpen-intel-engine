// Barrel exports for the BaseballOS intelligence presentation primitives.
//
// These components own presentation only. Every value they render is supplied
// by a governed application contract; none of them derives a state, a score, a
// ranking, or an explanation of its own.
export { default as IntelSection, SectionHeading } from './IntelSection'
export { default as EditionHeader } from './EditionHeader'
export { default as TeamStateChip, TeamStateRead } from './TeamStateChip'
export {
  default as EvidenceList,
  EvidenceRow,
  NamedArmReceipt,
  NamedArmReceipts,
} from './EvidenceReceipt'
export { default as TrustStrip, TrustFact } from './TrustStrip'
export { default as ConceptCard, ConceptGlossary } from './ConceptCard'
export { default as ConceptGlyph, CONCEPT_GLYPH_KEYS } from './ConceptGlyph'
export { default as IntelNotice, IntelSkeleton } from './IntelNotice'

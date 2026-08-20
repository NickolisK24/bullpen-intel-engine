import SectionState from '../../UI/SectionState'

export const PERFORMANCE_UNAVAILABLE_MESSAGE = 'A public team-scoped performance read is not available.'

export default function TeamBoardPerformance() {
  return (
    <section className="foundation-section" aria-labelledby="performance-title" data-testid="team-board-performance">
      <header className="mb-row">
        <h2 id="performance-title" className="type-section-title">Performance</h2>
        <p className="type-metadata mt-meta">Supporting performance context</p>
      </header>
      <SectionState
        status="unavailable"
        title="Performance unavailable"
        message={PERFORMANCE_UNAVAILABLE_MESSAGE}
      />
    </section>
  )
}

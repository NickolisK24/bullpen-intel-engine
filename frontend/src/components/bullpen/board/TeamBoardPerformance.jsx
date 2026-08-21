import SectionState from '../../UI/SectionState'

export const PERFORMANCE_UNAVAILABLE_MESSAGE = 'A public team-scoped performance read is not available.'

export default function TeamBoardPerformance() {
  return (
    <section className="foundation-section min-w-0" aria-labelledby="performance-title" data-testid="team-board-performance">
      <header className="mb-panel border-b border-line-subtle pb-panel">
        <div className="type-overline text-text-tertiary">Supporting context</div>
        <h2 id="performance-title" className="type-section-title mt-meta">Performance</h2>
        <p className="type-metadata mt-meta max-w-reading text-text-tertiary">Performance context remains secondary to current role and workload evidence.</p>
      </header>
      <div className="rounded-sm border border-line-subtle bg-surface-raised/20 p-panel">
        <SectionState
          status="unavailable"
          title="Performance unavailable"
          message={PERFORMANCE_UNAVAILABLE_MESSAGE}
        />
      </div>
    </section>
  )
}

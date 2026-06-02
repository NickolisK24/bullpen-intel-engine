const defaultRecommendationShell = {
  candidateName: 'Candidate not selected',
  statusLabel: 'Awaiting Candidate Evaluation',
  statusDetail: 'Future UI integration will render one candidate evaluation at a time.',
  categories: [
    'Use With Caution',
    'Avoid Tonight',
  ],
  explanations: [
    'Explanation content will come from the candidate-level recommendation response.',
  ],
  limitations: [
    'Limitation content must remain visible with every candidate evaluation.',
    'No final pitcher selection is made in this surface.',
  ],
  trust: {
    confidence: 'Pending candidate input',
    freshness: 'Pending data freshness',
    availability: 'Pending availability',
  },
  refusal: {
    reason: 'Refusal output will appear here when trusted data is missing, stale, low-confidence, or unavailable.',
  },
  metadata: {
    rankingApplied: false,
    selectionMade: false,
  },
}

function FieldBadge({ label, value }) {
  return (
    <div className="rounded border border-dirt bg-chalk/30 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{label}</div>
      <div className="mt-1 text-sm font-semibold text-chalk100">{value}</div>
    </div>
  )
}

function SectionCard({ title, children }) {
  return (
    <section className="rounded border border-dirt bg-field/40 p-4" aria-labelledby={`${title.replace(/\s+/g, '-').toLowerCase()}-heading`}>
      <h3 id={`${title.replace(/\s+/g, '-').toLowerCase()}-heading`} className="font-mono text-xs uppercase tracking-widest text-chalk400">
        {title}
      </h3>
      <div className="mt-3 text-sm leading-relaxed text-chalk200">{children}</div>
    </section>
  )
}

function TextList({ items, fallback }) {
  const values = Array.isArray(items) && items.length > 0 ? items : [fallback]

  return (
    <ul className="space-y-2">
      {values.map((item) => (
        <li key={item} className="rounded border border-dirt bg-chalk/20 px-3 py-2">
          {item}
        </li>
      ))}
    </ul>
  )
}

export default function RecommendationPanel({ model = defaultRecommendationShell }) {
  const recommendation = {
    ...defaultRecommendationShell,
    ...model,
    trust: {
      ...defaultRecommendationShell.trust,
      ...model.trust,
    },
    refusal: {
      ...defaultRecommendationShell.refusal,
      ...model.refusal,
    },
    metadata: {
      ...defaultRecommendationShell.metadata,
      ...model.metadata,
    },
  }

  return (
    <article className="card p-5 lg:p-6" aria-labelledby="recommendation-engine-v1-heading">
      <header className="mb-6 flex flex-col gap-3 border-b border-dirt pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="font-mono text-xs uppercase tracking-widest text-chalk400">Recommendation Engine V1</p>
          <h2 id="recommendation-engine-v1-heading" className="section-title mt-1">Candidate Evaluation</h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
            Candidate-level shell for future Recommendation Engine V1 display. This surface reserves
            space for trust-first output without ranking the bullpen or selecting a final pitcher.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:min-w-[22rem]">
          <FieldBadge label="Ranking" value="No Bullpen Ranking Applied" />
          <FieldBadge label="Selection" value="No Final Pitcher Selection Made" />
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]">
        <div className="space-y-4">
          <SectionCard title="Recommendation Status">
            <div className="rounded border border-amber/35 bg-amber/5 px-4 py-3">
              <div className="font-mono text-[11px] uppercase tracking-wider text-amber">Recommendation Status Area</div>
              <div className="mt-1 text-lg font-semibold text-chalk100">{recommendation.statusLabel}</div>
              <div className="mt-1 text-chalk400">{recommendation.statusDetail}</div>
              <div className="mt-3 font-mono text-xs text-chalk500">Candidate: {recommendation.candidateName}</div>
            </div>
          </SectionCard>

          <SectionCard title="Eligible Categories">
            <div className="mb-3 text-chalk400">
              Category eligibility is displayed as candidate-level guidance only.
            </div>
            <div className="flex flex-wrap gap-2">
              {recommendation.categories.map((category) => (
                <span key={category} className="rounded border border-dirt bg-chalk/30 px-3 py-1.5 font-mono text-xs text-chalk200">
                  {category}
                </span>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Explanation">
            <TextList
              items={recommendation.explanations}
              fallback="Explanation details will appear when a candidate response is available."
            />
          </SectionCard>

          <SectionCard title="Limitation">
            <TextList
              items={recommendation.limitations}
              fallback="Limitation details must remain visible with the result."
            />
          </SectionCard>
        </div>

        <aside className="space-y-4">
          <SectionCard title="Trust And Freshness">
            <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              <FieldBadge label="Confidence" value={recommendation.trust.confidence} />
              <FieldBadge label="Data Freshness" value={recommendation.trust.freshness} />
              <FieldBadge label="Availability" value={recommendation.trust.availability} />
            </div>
          </SectionCard>

          <SectionCard title="Refusal Output">
            <div className="rounded border border-dirt bg-chalk/20 px-3 py-2 text-chalk300">
              {recommendation.refusal.reason}
            </div>
          </SectionCard>

          <SectionCard title="Metadata">
            <dl className="grid gap-3">
              <div className="flex items-center justify-between gap-3 rounded border border-dirt bg-chalk/20 px-3 py-2">
                <dt className="font-mono text-xs text-chalk500">ranking_applied</dt>
                <dd className="font-mono text-sm font-semibold text-chalk100">{String(recommendation.metadata.rankingApplied)}</dd>
              </div>
              <div className="flex items-center justify-between gap-3 rounded border border-dirt bg-chalk/20 px-3 py-2">
                <dt className="font-mono text-xs text-chalk500">selection_made</dt>
                <dd className="font-mono text-sm font-semibold text-chalk100">{String(recommendation.metadata.selectionMade)}</dd>
              </div>
            </dl>
          </SectionCard>
        </aside>
      </div>
    </article>
  )
}

// The code-rendered Team State card (Share Cards SC-04B v1.2). It renders the
// immutable, backend-owned card blocks of a team-state-1.2.0 Share Artifact —
// artifact_context, team, state, readiness_summary, reliever_evidence, and trust —
// styled in the BaseballOS design system so a published artifact reads like a
// baseballos.app export, not a generated image. It performs NO baseball
// calculation, renders NO performance metric or league rank (none is carried),
// invents no team/state/count/label, and shows missing values honestly. Every
// number and sentence comes straight from the immutable artifact.

import { formatConfidence, getAvailabilityStatusLabel, READ_CONFIDENCE_FIELD_LABEL } from '../bullpen/availabilityView'
import SharedAvailabilityBadge from '../bullpen/AvailabilityBadge'
import {
  DATA_THROUGH_LABEL,
  GENERATED_AT_LABEL,
  PUBLISHED_AT_LABEL,
} from '../../utils/bullpenConcepts'
import { formatDateOnly, formatUtcDateTimeEt } from '../../utils/dateDisplay'

const SITE = 'BaseballOS'

// Reader-facing accent per public Team State (Fresh / Stretched / Vulnerable).
// Literal class strings so the Tailwind compiler keeps them. State colour is used
// only on the state itself — never as decoration elsewhere.
const STATE_ACCENT = {
  fresh: { border: 'border-pine/50', bg: 'bg-pine/10', dot: 'bg-pine' },
  stretched: { border: 'border-warning/50', bg: 'bg-warning/10', dot: 'bg-warning' },
  vulnerable: { border: 'border-danger/50', bg: 'bg-danger/10', dot: 'bg-danger' },
}
const NEUTRAL_ACCENT = { border: 'border-dirt', bg: 'bg-chalk/10', dot: 'bg-chalk500' }

// The four readiness_summary metrics, in a fixed display order. Keys match the
// backend contract; the card never computes or reorders them.
const READINESS_METRICS = [
  'clean_options',
  'multi_use_arms',
  'short_rest_arms',
  'left_handed_options',
]

function accentFor(publicState) {
  return STATE_ACCENT[publicState] || NEUTRAL_ACCENT
}

function fmtDate(value) {
  return formatDateOnly(value, { month: 'long' })
}

function fmtDateTime(value) {
  return formatUtcDateTimeEt(value)
}

function GlanceMetric({ metric }) {
  if (!metric) return null
  const hasCounts = Number.isFinite(metric.count) && Number.isFinite(metric.total)
  return (
    <div className="border border-dirt bg-field/40 px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {metric.label || 'Readiness'}
      </p>
      <p className="mt-1 font-display text-2xl leading-none tracking-wide text-chalk100">
        {hasCounts ? (
          <>
            {metric.count}
            <span className="ml-1 text-base text-chalk500">of {metric.total}</span>
          </>
        ) : (
          <span className="text-chalk500">—</span>
        )}
      </p>
      {metric.statement ? (
        <p className="mt-1 text-xs leading-snug text-chalk400">{metric.statement}</p>
      ) : null}
    </div>
  )
}

function EvidenceCell({ label, children, className = '' }) {
  return (
    <div className={className}>
      <span className="mb-0.5 block font-mono text-[10px] uppercase tracking-widest text-chalk600 sm:hidden">
        {label}
      </span>
      <span className="text-chalk200">{children}</span>
    </div>
  )
}

function RelieverRow({ row }) {
  const availabilityLabel = getAvailabilityStatusLabel(row.availability)
  const appearances = Number.isFinite(row.last_three_appearances) ? row.last_three_appearances : null
  const appearanceText =
    appearances === null
      ? '—'
      : `${appearances} ${appearances === 1 ? 'game' : 'games'}${
          row.innings_text ? ` · ${row.innings_text} IP` : ''
        }`
  const lastDate = fmtDate(row.last_appearance_date)
  const lastText = lastDate
    ? `${lastDate}${row.last_opponent ? ` vs ${row.last_opponent}` : ''}`
    : '—'
  const restText =
    row.rest_days === null || row.rest_days === undefined
      ? '—'
      : `${row.rest_days} ${row.rest_days === 1 ? 'day' : 'days'}`

  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-2 border-t border-dirt px-4 py-3 text-sm sm:grid-cols-[2fr_1.4fr_1.8fr_1fr_1.2fr] sm:items-center sm:gap-y-0">
      <EvidenceCell label="Reliever" className="col-span-2 sm:col-span-1">
        <span className="font-medium text-chalk100">{row.name || '—'}</span>
      </EvidenceCell>
      <EvidenceCell label="Last 3 games">{appearanceText}</EvidenceCell>
      <EvidenceCell label="Last appearance">
        {lastDate ? (
          <time dateTime={row.last_appearance_date}>{lastText}</time>
        ) : (
          lastText
        )}
      </EvidenceCell>
      <EvidenceCell label="Rest">{restText}</EvidenceCell>
      <EvidenceCell label="Availability">
        {availabilityLabel ? (
          <SharedAvailabilityBadge
            availability={{ availability_status: row.availability, availability_public_label: availabilityLabel }}
            compact
          />
        ) : <span className="text-chalk500">—</span>}
      </EvidenceCell>
    </div>
  )
}

export default function TeamStateArtifactCard({ card }) {
  if (!card) return null
  const ctx = card.artifact_context || {}
  const team = card.team || {}
  const state = card.state || {}
  const summary = card.readiness_summary || {}
  const relievers = Array.isArray(card.reliever_evidence) ? card.reliever_evidence : []
  const trust = card.trust || {}
  const limitations = Array.isArray(card.limitations) ? card.limitations : []

  const teamName = team.canonical_name || 'This team'
  const publicLabel = state.public_label || 'Team State'
  const accent = accentFor(state.public_state)
  const dataThroughText = fmtDate(ctx.data_through)

  return (
    <article
      className="team-state-card overflow-hidden rounded-lg border border-dirt bg-field/60"
      data-public-state={state.public_state || ''}
      data-card-version={card.card_version || ''}
    >
      {/* Header — masthead, not a generated logo. */}
      <header className="border-b border-dirt px-5 py-3 sm:px-6">
        <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-amber">
            {SITE} <span className="text-chalk500">· Bullpen Intelligence</span>
          </p>
          {dataThroughText ? (
            <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Data through <time dateTime={ctx.data_through}>{dataThroughText}</time>
            </p>
          ) : null}
        </div>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-chalk600">
          Team Bullpen State
        </p>
      </header>

      {/* Hero — team, state, why. */}
      <div className={`border-b border-dirt px-5 pb-5 pt-4 sm:px-6 ${accent.bg}`}>
        <p className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
          {teamName}
          {team.abbreviation ? <span className="ml-2 text-chalk600">({team.abbreviation})</span> : null}
        </p>
        <h1 className="mt-1 flex items-center gap-2 font-display text-4xl leading-none tracking-wide text-chalk100 sm:text-5xl">
          <span className={`inline-block h-3 w-3 shrink-0 rounded-full ${accent.dot}`} aria-hidden="true" />
          <span className="min-w-0 break-words">{publicLabel}</span>
        </h1>
        {state.why ? (
          <p className="mt-3 max-w-prose text-base leading-relaxed text-chalk200">{state.why}</p>
        ) : null}
      </div>

      {/* Bullpen at a Glance — the four readiness metrics. */}
      <section aria-labelledby="card-glance" className="px-5 py-4 sm:px-6">
        <h2 id="card-glance" className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
          Bullpen at a glance
        </h2>
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {READINESS_METRICS.map((key) => (
            <GlanceMetric key={key} metric={summary[key]} />
          ))}
        </div>
      </section>

      {/* Current Bullpen Evidence — governed reliever rows, no scroll on mobile. */}
      <section aria-labelledby="card-evidence" className="border-t border-dirt px-1 py-4 sm:px-2">
        <h2
          id="card-evidence"
          className="px-4 font-mono text-[11px] uppercase tracking-widest text-chalk500 sm:px-4"
        >
          Current bullpen evidence
        </h2>
        {relievers.length ? (
          <div className="mt-2" role="table" aria-label="Current bullpen evidence">
            <div
              className="hidden px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-chalk500 sm:grid sm:grid-cols-[2fr_1.4fr_1.8fr_1fr_1.2fr]"
              role="row"
            >
              <span role="columnheader">Reliever</span>
              <span role="columnheader">Last 3 games</span>
              <span role="columnheader">Last appearance</span>
              <span role="columnheader">Rest</span>
              <span role="columnheader">Availability</span>
            </div>
            {relievers.map((row, index) => (
              <RelieverRow key={row.pitcher_id ?? index} row={row} />
            ))}
          </div>
        ) : (
          <p className="mt-2 px-4 text-sm text-chalk400">
            No reliever evidence was recorded on this artifact.
          </p>
        )}
      </section>

      {/* Trust strip. */}
      <section aria-labelledby="card-trust" className="border-t border-dirt px-5 py-4 sm:px-6">
        <h2 id="card-trust" className="sr-only">
          Trust and freshness
        </h2>
        {trust.source_statement ? (
          <p className="text-sm leading-relaxed text-chalk300">{trust.source_statement}</p>
        ) : null}
        {trust.coverage_statement ? (
          <p className="mt-1 text-xs leading-relaxed text-chalk500">{trust.coverage_statement}</p>
        ) : null}
        <dl className="mt-3 grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{READ_CONFIDENCE_FIELD_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">{formatConfidence(trust.confidence)}</dd>
          </div>
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{DATA_THROUGH_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">
              {dataThroughText ? <time dateTime={ctx.data_through}>{dataThroughText}</time> : '—'}
            </dd>
          </div>
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">Source</dt>
            <dd className="mt-0.5 text-chalk200">{ctx.publication_label || '—'}</dd>
          </div>
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{GENERATED_AT_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">
              {fmtDateTime(ctx.generated_at) ? (
                <time dateTime={ctx.generated_at}>{fmtDateTime(ctx.generated_at)}</time>
              ) : (
                '—'
              )}
            </dd>
          </div>
        </dl>
      </section>

      {/* Limitations — only when a durable one exists. */}
      {limitations.length ? (
        <section aria-labelledby="card-limitations" className="border-t border-dirt px-5 py-4 sm:px-6">
          <h2
            id="card-limitations"
            className="font-mono text-[11px] uppercase tracking-widest text-chalk500"
          >
            Limitations
          </h2>
          <ul className="mt-2 space-y-1">
            {limitations.map((text, index) => (
              <li key={index} className="text-sm leading-relaxed text-chalk300">
                {text}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Footer — masthead, immutability note. */}
      <footer className="border-t border-dirt px-5 py-3 sm:px-6">
        <p className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
          {SITE} · Bullpen Intelligence · Immutable published artifact
        </p>
      </footer>
    </article>
  )
}

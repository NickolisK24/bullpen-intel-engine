import { Link } from 'react-router-dom'
import { EmptyState, FreshnessStamp } from '../../UI'
import { buildComparisonHref, buildTeamBoardHref, normalizeTeamReference } from '../../../utils/evidenceLinks'
import { EVIDENCE_CARD_ORIGIN } from '../../../utils/shareCardArtifact'
import EvidenceShareMenu from '../../share/EvidenceShareMenu'
import { getComparisonView } from './teamBullpenComparisonView'

function TeamState({ label, state }) {
  return (
    <div className="space-y-1">
      <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{label}</p>
      {state.available ? (
        <div>
          <span
            className="inline-flex min-h-7 items-center gap-1.5 rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-wider"
            style={{ borderColor: state.tone.borderColor, backgroundColor: state.tone.backgroundColor, color: state.tone.color }}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: state.tone.dot }} aria-hidden="true" />
            {state.publicLabel}
          </span>
        </div>
      ) : (
        <p className="text-xs leading-relaxed text-chalk500">{state.unavailableMessage}</p>
      )}
    </div>
  )
}

function DomainSection({ domain, labelA, labelB }) {
  return (
    <section className="border-t border-dirt py-5" aria-labelledby={`comparison-${domain.key}`}>
      <h3 id={`comparison-${domain.key}`} className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">{domain.label}</h3>
      {domain.status === 'withheld' ? (
        <p className="text-sm text-chalk500">{domain.message}</p>
      ) : (
        <>
          <div className="hidden grid-cols-[minmax(9rem,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-x-6 gap-y-2 md:grid">
            <span aria-hidden="true" />
            <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{labelA}</p>
            <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{labelB}</p>
            {domain.rows.map(row => (
              <div key={row.key} className="contents">
                <p className="text-sm text-chalk400">{row.label}</p>
                <p className="font-mono text-sm text-chalk100">{row.valueA}</p>
                <p className="font-mono text-sm text-chalk100">{row.valueB}</p>
              </div>
            ))}
          </div>
          <div className="grid gap-4 md:hidden">
            {[[labelA, 'valueA'], [labelB, 'valueB']].map(([label, valueKey]) => (
              <div key={label} className="border-l border-dirt pl-3">
                <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-chalk500">{label}</p>
                <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5">
                  {domain.rows.map(row => (
                    <div key={row.key} className="contents">
                      <dt className="text-sm text-chalk400">{row.label}</dt>
                      <dd className="font-mono text-sm text-chalk100">{row[valueKey]}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
          {domain.limitations.length > 0 && (
            <ul className="mt-3 space-y-1">
              {domain.limitations.map((limitation, index) => (
                <li key={index} className="text-xs leading-relaxed text-chalk500">• {limitation}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}

export default function BullpenComparisonView({ payload }) {
  const view = getComparisonView(payload)
  if (!view.hasComparison) return <EmptyState title="Comparison unavailable" subtitle="This comparison could not be established from the current publication." />

  const teamARef = normalizeTeamReference(view.teamA)
  const teamBRef = normalizeTeamReference(view.teamB)
  const destinationPath = buildComparisonHref(teamARef, teamBRef, { section: 'comparison-evidence' })
  const destinationUrl = teamARef && teamBRef ? `${EVIDENCE_CARD_ORIGIN}${destinationPath}` : null
  const cardModel = null
  const shareText = cardModel?.shareText || `Current ${view.labelA} and ${view.labelB} bullpen operating conditions on BaseballOS.`

  return (
    <div className="space-y-6">
      <section aria-labelledby="current-bullpen-comparison-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="current-bullpen-comparison-heading" className="font-mono text-xs uppercase tracking-widest text-chalk400">Current Bullpen Comparison</h2>
            {view.representedDate && <FreshnessStamp freshness={{ data_through: view.representedDate }} showExceptional={false} className="mt-2" />}
          </div>
          <p className="text-xs text-chalk500">Aligned facts from one published snapshot.</p>
        </div>

        <div className="grid gap-3 border-y border-dirt py-4 md:grid-cols-2 md:gap-8">
          <TeamState label={view.labelA} state={view.teamStateA} />
          <TeamState label={view.labelB} state={view.teamStateB} />
        </div>
        {view.teamStateStatus === 'withheld' && <p className="border-b border-dirt py-3 text-sm text-chalk500">{view.teamStateMessage}</p>}

        <div id="comparison-evidence" tabIndex={-1} className="scroll-mt-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
          {view.domains.map(domain => <DomainSection key={domain.key} domain={domain} labelA={view.labelA} labelB={view.labelB} />)}
        </div>
      </section>

      <section aria-labelledby="comparison-team-boards-heading">
        <h2 id="comparison-team-boards-heading" className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Full Team Boards</h2>
        <div className="flex flex-wrap gap-3">
          <TeamBoardLink team={view.teamA} label={view.labelA} />
          <TeamBoardLink team={view.teamB} label={view.labelB} />
        </div>
      </section>

      <div className="flex justify-end border-t border-dirt pt-4">
        <EvidenceShareMenu
          cardModel={cardModel}
          destinationUrl={destinationUrl}
          shareText={shareText}
          context={{ surface: 'compare_bullpens', cardType: 'comparison', team_a_ref: teamARef, team_b_ref: teamBRef, evidence_target: 'comparison_evidence', data_through: view.representedDate }}
        />
      </div>
    </div>
  )
}

function TeamBoardLink({ team, label }) {
  const href = team?.team_board_href || buildTeamBoardHref(team, { source: 'comparison' })
  if (!href) return null
  return (
    <Link to={href} className="inline-flex min-h-10 items-center rounded border border-dirt px-4 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber">
      Open the {label} board →
    </Link>
  )
}

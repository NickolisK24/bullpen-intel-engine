import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import {
  getBullpenDashboard,
  getLeagueTeamStateBoard,
  getTeams,
  getTodayIntelligence,
  getTonightIntelligence,
} from '../../utils/api'
import { getLeadStoryView, getTonightCards } from '../home/IntelligenceSurface'
import { displayDate, ProductPageHeader, QuietState, StateRead } from './ProductPrimitives'

function EvidenceRows({ items = [] }) {
  return (
    <div className="mt-6 grid border-y border-line md:grid-cols-3">
      {items.slice(0, 3).map((item, index) => (
        <div key={`${index}-${item}`} className="grid grid-cols-[2rem_1fr] gap-3 border-line py-4 md:border-r md:px-4 md:first:pl-0 md:last:border-r-0">
          <span className="font-mono text-[10px] text-brass/70">E{index + 1}</span>
          <p className="text-sm leading-6 text-chalk300">{item}</p>
        </div>
      ))}
    </div>
  )
}

function TonightCard({ card }) {
  return (
    <article className="border border-line bg-panel p-5">
      <p className="bos-eyebrow text-chalk500">{card.label || 'Tonight'}</p>
      <h4 className="mt-2 font-display text-xl font-semibold text-chalk100">{card.headline}</h4>
      <p className="mt-3 text-sm leading-6 text-chalk400">{card.summary}</p>
      {card.teamName && <p className="mt-4 font-mono text-[11px] text-chalk500">{card.teamName}</p>}
      {card.href && <Link to={card.href} className="bos-link mt-3">Inspect the team board →</Link>}
    </article>
  )
}

export default function DailyEdition() {
  const teams = useFetch(getTeams)
  const leadRequest = useFetch(getTodayIntelligence)
  const tonightRequest = useFetch(getTonightIntelligence)
  const leagueRequest = useFetch(getLeagueTeamStateBoard)
  const dashboardRequest = useFetch(getBullpenDashboard)

  const lead = getLeadStoryView(leadRequest.data, teams.data || [])
  const tonight = getTonightCards(tonightRequest.data, teams.data || [], 2)
  const league = leagueRequest.data
  const freshness = league?.freshness || dashboardRequest.data?.freshness || {}
  const baseballDate = tonightRequest.data?.reference_date || freshness.reference_date
  const currentGroups = (league?.groups || []).filter(group => group.key !== 'withheld')
  const changed = dashboardRequest.data?.what_changed_since_yesterday
  const changedItems = changed?.state === 'available' ? changed.items || [] : []

  return (
    <div className="bos-page py-8 md:py-10">
      <ProductPageHeader
        eyebrow="Daily Edition"
        title={displayDate(baseballDate, { weekday: true }) || 'Today'}
        facts={[
          { label: 'Data through', value: displayDate(freshness.data_through) },
          { label: 'League read', value: league ? `${league.teams_in_current_state} of ${league.teams_expected} clubs represented` : null },
        ]}
      />

      <div className="grid gap-10 py-9 lg:grid-cols-[minmax(0,1fr)_21rem] lg:gap-14">
        <div>
          <p className="bos-eyebrow text-chalk500">Today's Lead</p>
          {lead.hasStory ? (
            <article className="mt-4">
              <h2 className="max-w-[20ch] font-display text-[2.15rem] font-semibold leading-[1.14] text-chalk100 md:text-[2.65rem]">
                {lead.headline}
              </h2>
              {lead.team?.teamName && <p className="mt-4 font-mono text-[11px] text-chalk500">{lead.team.teamName}</p>}
              {lead.body && <p className="mt-5 max-w-measure text-[1rem] leading-7 text-chalk300">{lead.body}</p>}
              <EvidenceRows items={lead.evidence} />
              {lead.team?.teamId && (
                <Link to={`/bullpen?view=board&team=${lead.team.teamId}&source=today`} className="bos-action bos-action--primary mt-6">
                  Inspect this bullpen →
                </Link>
              )}
            </article>
          ) : (
            <QuietState title="Quiet lead">{lead.emptyReason || 'No supported lead observation is publishable for this edition.'}</QuietState>
          )}
        </div>

        <aside className="space-y-8">
          <section>
            <p className="bos-eyebrow text-chalk500">Across MLB</p>
            <div className="mt-3 divide-y divide-line">
              {currentGroups.map(group => (
                <div key={group.key} className="flex items-center justify-between py-3">
                  <StateRead state={group.key} label={group.label} />
                  <span className="font-mono text-xs text-chalk300">{group.count} clubs</span>
                </div>
              ))}
            </div>
            {league?.teams_withheld > 0 && (
              <p className="mt-4 text-xs leading-5 text-chalk500">{league.teams_withheld} clubs withheld because a current Team State could not be supported.</p>
            )}
            <Link to="/dashboard" className="bos-action bos-action--quiet mt-4 w-full">Open league board →</Link>
          </section>

          <section>
            <p className="bos-eyebrow text-chalk500">What changed</p>
            {changedItems.length > 0 ? (
              <div className="mt-3 divide-y divide-line">
                {changedItems.slice(0, 4).map((item, index) => (
                  <div key={item.key || index} className="py-3">
                    <p className="text-sm text-chalk200">{item.public_headline || item.public_summary}</p>
                    {item.public_summary && item.public_headline && <p className="mt-1 text-xs leading-5 text-chalk500">{item.public_summary}</p>}
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm leading-6 text-chalk500">No trusted, comparable snapshot change is available for this edition.</p>
            )}
          </section>
        </aside>
      </div>

      <section className="border-t border-line py-9">
        <div className="flex items-end justify-between gap-5">
          <div>
            <p className="bos-eyebrow text-brass">Tonight</p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-chalk100">What tonight asks of these bullpens</h2>
          </div>
          <Link to="/slate" className="bos-link">Full slate →</Link>
        </div>
        {tonight.length > 0 ? (
          <div className="mt-6 grid gap-5 lg:grid-cols-2">{tonight.map(card => <TonightCard key={card.key} card={card} />)}</div>
        ) : (
          <div className="mt-6"><QuietState title="Tonight">{tonightRequest.data?.empty_reason === 'no_teams_playing_today' ? 'No MLB games are scheduled for this baseball date.' : 'No supported pregame bullpen condition is publishable yet.'}</QuietState></div>
        )}
      </section>
    </div>
  )
}

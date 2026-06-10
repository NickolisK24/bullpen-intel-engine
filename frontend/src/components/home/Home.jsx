import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard, getBullpenObservations, getTeams } from '../../utils/api'
import { LoadingPane, ErrorState } from '../UI'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import LeagueIntelligenceCards from './LeagueIntelligenceCards'
import BullpenStories from './BullpenStories'
import RankingsPreview from './RankingsPreview'
import TeamExplorer from './TeamExplorer'
import {
  getBullpenStories,
  getHeroStory,
  getLeagueCards,
  getMastheadView,
  getRankingsPreview,
  getTeamExplorerView,
  homeTone,
} from './homeIntelligenceView'

// The Morning Bullpen Report — BaseballOS's story-led front page. Leads with
// the most interesting bullpen situation in baseball today, then opens doors
// into the rest of the platform. Reads like a baseball publication; every
// number underneath comes from the same league dashboard, landscape, and
// governed observation outputs the deeper pages already use.
export default function Home() {
  const dash = useFetch(getBullpenDashboard)
  const teams = useFetch(getTeams)
  // Observations enrich the story list when the governed feed has content;
  // the page never blocks on them (only .data is read, so a failed fetch
  // simply means no observation stories).
  const observations = useFetch(getBullpenObservations)

  return (
    <HomeView
      dashboard={dash.data}
      teams={teams.data}
      observations={observations.data}
      loading={dash.loading}
      error={dash.error}
      onRetry={dash.refetch}
    />
  )
}

export function HomeView({
  dashboard,
  teams,
  observations = null,
  loading = false,
  error = null,
  onRetry,
}) {
  const masthead = getMastheadView(dashboard)
  const hero = getHeroStory(dashboard)
  const cards = getLeagueCards(dashboard)
  const stories = getBullpenStories(dashboard, observations)
  const rankings = getRankingsPreview(dashboard)
  const explorer = getTeamExplorerView(teams, dashboard)

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      <Masthead masthead={masthead} />

      {loading && !dashboard ? (
        <LoadingPane message="Pulling together this morning's bullpen report..." />
      ) : error && !dashboard ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <>
          <HeroStory hero={hero} />
          <LeagueIntelligenceCards cards={cards} />
          <BullpenStories stories={stories} />
          <RankingsPreview rankings={rankings} />
        </>
      )}

      <TeamExplorer explorer={explorer} />

      <FeedbackCTA
        compact
        className="mb-2"
        eyebrow="User Validation"
        title="Help shape BaseballOS"
        body="Share what is useful, unclear, or missing while BaseballOS is being tested with real users."
      />
    </div>
  )
}

function Masthead({ masthead }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3 border-b border-dirt pb-4 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
      <div>
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
          The Morning Bullpen Report
        </div>
        <h1 className="mt-1 font-display text-4xl tracking-wider text-chalk100 leading-none">
          BASEBALL<span className="text-gradient-amber">OS</span> TODAY
        </h1>
      </div>
      <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-chalk400">
        <span>{masthead.editionDate}</span>
        <span className="text-chalk600" aria-hidden="true">·</span>
        <span className="rounded border border-dirt bg-dugout px-2 py-1 text-chalk400">
          {masthead.dataLine}
        </span>
        <Link
          to="/dashboard"
          className="rounded border border-dirt bg-dugout px-2 py-1 text-chalk200 transition-colors hover:border-amber/40 hover:text-amber"
        >
          League dashboard →
        </Link>
      </div>
    </header>
  )
}

// Section 1 — What BaseballOS Sees Today: one flagship observation, told the
// way a baseball writer would lead a column.
function HeroStory({ hero }) {
  const tone = homeTone(hero.tone)

  return (
    <section className="mb-8" aria-label="What BaseballOS sees today">
      <div className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">
        What BaseballOS Sees Today
      </div>

      <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout bg-stadium-glow p-5 sm:p-7">
        <div className="absolute inset-0 bg-grid-lines opacity-100 pointer-events-none" />
        <div className="relative z-10">
          <span
            className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
            style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
            {hero.kicker}
          </span>

          <h2 className="mt-3 max-w-4xl font-display text-4xl leading-none tracking-wide text-chalk100 sm:text-5xl">
            {hero.headline}
          </h2>

          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-chalk200 sm:text-base">
            {hero.observation}
          </p>

          <div className="mt-4 max-w-3xl rounded border-l-4 border-amber/70 bg-field/60 p-3 sm:p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">Why It Matters</div>
            <p className="mt-1 text-sm leading-relaxed text-chalk200">{hero.whyItMatters}</p>
          </div>

          {hero.chips.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {hero.chips.map(chip => (
                <span
                  key={chip.key}
                  className="inline-flex items-center gap-2 rounded border border-dirt bg-field/60 px-2.5 py-1 font-mono text-[11px] text-chalk400"
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: homeTone(chip.tone).dot }} aria-hidden="true" />
                  {chip.label}
                  <span className="text-sm text-chalk100">{chip.value}</span>
                </span>
              ))}
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            {hero.team?.href && (
              <Link
                to={hero.team.href}
                className="rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
              >
                Step inside the {hero.team.abbr || hero.team.teamName} pen →
              </Link>
            )}
            <Link
              to="/bullpen"
              className="rounded border border-dirt bg-field/60 px-4 py-2 font-mono text-xs uppercase tracking-wider text-chalk200 transition-colors hover:border-amber/40 hover:text-amber"
            >
              Browse every bullpen →
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

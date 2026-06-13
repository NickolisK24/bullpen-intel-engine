import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { LoadingPane, ErrorState } from '../UI'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import BullpenStories, { SectionHeading, StoryContinuityNote } from './BullpenStories'
import {
  getHeroStory,
  getLeagueContext,
  getMastheadView,
  getTodayWatchItems,
  homeTone,
} from './homeIntelligenceView'

// The Morning Bullpen Report — BaseballOS's story-led front page. Curated,
// not exhaustive: one flagship observation, three things to watch, short
// league context, and a handoff to Stories. The Stories page carries the
// browseable feed and the Bullpen page remains the team directory.
export default function Home() {
  const dash = useFetch(getBullpenDashboard)

  return (
    <HomeView
      dashboard={dash.data}
      loading={dash.loading}
      error={dash.error}
      onRetry={dash.refetch}
    />
  )
}

export function HomeView({
  dashboard,
  loading = false,
  error = null,
  onRetry,
}) {
  const masthead = getMastheadView(dashboard)
  const hero = getHeroStory(dashboard)
  const watchItems = getTodayWatchItems(dashboard)
  const leagueContext = getLeagueContext(dashboard)

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      <Masthead masthead={masthead} />

      {loading && !dashboard ? (
        <LoadingPane message="Pulling together this morning's bullpen report..." />
      ) : error && !dashboard ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <>
          <section className="mb-8" aria-label="What BaseballOS sees today">
            <div className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">
              What BaseballOS Sees Today
            </div>
            <HeroStory hero={hero} />
          </section>
          <BullpenStories stories={watchItems} showCta={false} />
          <LeagueContext context={leagueContext} />
        </>
      )}

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

// The flagship observation, told the way a baseball writer would lead a
// column. Stories deliberately explores the observations behind and beyond it.
function HeroStory({ hero }) {
  const tone = homeTone(hero.tone)

  return (
    <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout bg-stadium-glow p-5 sm:p-7">
      <div className="absolute inset-0 bg-grid-lines opacity-100 pointer-events-none" />
      <div className="relative z-10">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
            style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
            {hero.kicker}
          </span>
          {hero.read && (
            <span
              className="inline-flex items-center gap-1.5 rounded border border-dirt bg-field/60 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-chalk200"
              title={`${hero.read.display}: ${hero.read.detail}`}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: homeTone(hero.read.tone).dot }} aria-hidden="true" />
              {hero.read.display}
            </span>
          )}
        </div>

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

        <StoryContinuityNote note={hero.continuity_note} className="mt-4 max-w-3xl" />

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
  )
}

function LeagueContext({ context }) {
  return (
    <section className="mb-8" aria-label="League context">
      <SectionHeading
        title="League Context"
        subtitle="The short read behind the morning briefing."
      />

      <div className="border border-dirt bg-dugout p-4 sm:p-5">
        <p className="max-w-3xl text-sm leading-relaxed text-chalk300">
          {context.summary}
        </p>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {context.facts.map(fact => {
            const tone = homeTone(fact.tone)
            return (
              <div key={fact.key} className="border border-dirt bg-field/50 p-3">
                <div
                  className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
                  style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
                >
                  <span className="h-1 w-1 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
                  {fact.label}
                </div>
                <div className="mt-2 font-display text-2xl leading-none tracking-wide text-chalk100">
                  {fact.value}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-chalk500">{fact.detail}</p>
              </div>
            )
          })}
        </div>

        <div className="mt-4 text-right">
          <Link
            to={context.href}
            className="inline-flex items-center rounded border border-amber/40 bg-amber/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-amber transition-colors hover:bg-amber/20"
          >
            {context.cta} →
          </Link>
        </div>
      </div>
    </section>
  )
}

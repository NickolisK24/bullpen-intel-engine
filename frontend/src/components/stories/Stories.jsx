import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard, getBullpenObservations } from '../../utils/api'
import { LoadingPane, ErrorState } from '../UI'
import LeagueIntelligenceCards from '../home/LeagueIntelligenceCards'
import { SectionHeading } from '../home/BullpenStories'
import {
  getHeroStory,
  getLeagueCards,
  getMastheadView,
  homeTone,
} from '../home/homeIntelligenceView'
import {
  FEED_EMPTY_COPY,
  STORY_FILTERS,
  filterStoryFeed,
  getFilterCounts,
  getStoryFeed,
} from './storiesFeedView'

// BaseballOS Stories — the browseable bullpen intelligence feed. Today is the
// curated morning briefing; this page is the stream: a compact top story,
// filters up front, and every storyline BaseballOS is carrying right now.
// Same derivations, same destinations, no new signals.
export default function Stories() {
  const dash = useFetch(getBullpenDashboard)
  const observations = useFetch(getBullpenObservations)

  return (
    <StoriesView
      dashboard={dash.data}
      observations={observations.data}
      loading={dash.loading}
      error={dash.error}
      onRetry={dash.refetch}
    />
  )
}

export function StoriesView({
  dashboard,
  observations = null,
  loading = false,
  error = null,
  onRetry,
  initialFilter = 'all',
}) {
  const [filter, setFilter] = useState(initialFilter)
  const masthead = getMastheadView(dashboard)
  const hero = getHeroStory(dashboard, 'stories-top')
  const cards = getLeagueCards(dashboard)
  const feed = getStoryFeed(dashboard, observations)
  const counts = getFilterCounts(feed.items)
  const visible = filterStoryFeed(feed.items, filter)

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      <header className="mb-5 border-b border-dirt pb-4 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
              The Bullpen Intelligence Feed
            </div>
            <h1 className="mt-1 font-display text-4xl tracking-wider text-chalk100 leading-none">
              BASEBALL<span className="text-gradient-amber">OS</span> STORIES
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-chalk400">
            <span className="rounded border border-dirt bg-dugout px-2 py-1">{masthead.dataLine}</span>
            <span className="rounded border border-amber/30 bg-amber/5 px-2 py-1 text-amber/80">
              Observations, not predictions.
            </span>
          </div>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
          The bullpen stories BaseballOS is watching today — built from current workload and
          availability signals.
        </p>
      </header>

      {loading && !dashboard ? (
        <LoadingPane message="Gathering today's bullpen stories..." />
      ) : error && !dashboard ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <>
          <TopStoryCard hero={hero} />

          <section className="mb-8" aria-label="Story feed">
            <SectionHeading
              title="The Story Feed"
              subtitle="Every storyline BaseballOS is carrying today. Pick a lane or read it all."
            />

            <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Story filters">
              {STORY_FILTERS.map(option => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setFilter(option.key)}
                  aria-pressed={filter === option.key}
                  className={`rounded border px-3 py-1.5 font-mono text-xs transition-all ${
                    filter === option.key
                      ? 'border-amber/40 bg-amber/10 text-amber'
                      : 'border-dirt text-chalk400 hover:border-chalk400'
                  }`}
                >
                  {option.label}
                  <span className="ml-1.5 opacity-60">{counts[option.key] ?? 0}</span>
                </button>
              ))}
            </div>

            {visible.length === 0 ? (
              <div className="card p-5 text-sm text-chalk400">
                {FEED_EMPTY_COPY[filter] || feed.fallback}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {visible.map((story, index) => (
                  <FeedStoryCard key={`${story.kicker}-${story.teamId ?? 'league'}-${index}`} story={story} />
                ))}
              </div>
            )}
          </section>

          <section className="mb-8" aria-label="Around the league">
            <SectionHeading
              title="Around The League"
              subtitle="The four situations framing the day — the same cards the morning briefing leads with."
            />
            <LeagueIntelligenceCards cards={cards} />
          </section>
        </>
      )}
    </div>
  )
}

// The feed's lede: the same flagship story Today leads with, in a compact cut
// that hands the page to the feed instead of repeating the homepage hero.
function TopStoryCard({ hero }) {
  const tone = homeTone(hero.tone)
  const href = hero.team?.href || null

  const inner = (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-widest text-amber/70">Top Story</span>
        <span
          className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
          style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
        >
          <span className="h-1 w-1 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
          {hero.kicker}
        </span>
      </div>

      <h2 className="mt-2 max-w-4xl font-display text-2xl leading-tight tracking-wide text-chalk100 sm:text-3xl group-hover:text-amber transition-colors">
        {hero.headline}
      </h2>

      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">{hero.observation}</p>

      {href && (
        <div className="mt-3 font-mono text-[10px] uppercase tracking-widest text-chalk600 group-hover:text-amber transition-colors">
          Step inside the {hero.team.abbr || hero.team.teamName} pen →
        </div>
      )}
    </>
  )

  return (
    <section className="mb-6" aria-label="Top story">
      {href ? (
        <Link
          to={href}
          className="card group block p-4 sm:p-5 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5"
        >
          {inner}
        </Link>
      ) : (
        <article className="card p-4 sm:p-5">{inner}</article>
      )}
    </section>
  )
}

// A feed entry — the Today story card in a roomier cut, with the club named
// when the story belongs to one.
function FeedStoryCard({ story }) {
  const tone = homeTone(story.tone)
  const hasDestination = Boolean(story.href)

  const inner = (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span
          className="inline-flex w-fit items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
          style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
        >
          <span className="h-1 w-1 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
          {story.kicker}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
          {story.teamId != null && story.abbr ? `${story.abbr} · ${story.teamName}` : 'Around the league'}
        </span>
      </div>

      {story.read && (
        <div
          className="mt-1.5 inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-chalk500"
          title={`${story.read.display}: ${story.read.detail}`}
        >
          <span className="h-1 w-1 rounded-full" style={{ backgroundColor: homeTone(story.read.tone).dot }} aria-hidden="true" />
          {story.read.display}
        </div>
      )}

      <h3 className="mt-3 font-display text-2xl leading-tight tracking-wide text-chalk100 group-hover:text-amber transition-colors">
        {story.title}
      </h3>

      <p className="mt-2 flex-1 text-sm leading-relaxed text-chalk400">{story.body}</p>

      {hasDestination && (
        <div className="mt-3 font-mono text-[10px] uppercase tracking-widest text-chalk600 group-hover:text-amber transition-colors">
          {story.cta || 'Open the full picture'} →
        </div>
      )}
    </>
  )

  if (!hasDestination) {
    return <article className="card flex flex-col p-5">{inner}</article>
  }

  return (
    <Link
      to={story.href}
      className="card group flex flex-col p-5 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5"
    >
      {inner}
    </Link>
  )
}

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { formatTeamLabel } from '../../utils/formatters'
import { LoadingPane, ErrorState, StaleDataNotice } from '../UI'
import { SectionHeading, StoryDisclosureNote } from '../home/BullpenStories'
import {
  getMastheadView,
  homeTone,
} from '../home/homePresentationView'
import TeamShareButton from '../share/TeamShareButton'
import {
  DEFAULT_STORY_FILTER,
  STORY_FILTERS,
  filterStoryFeed,
  getActiveStoryFilterLabel,
  getFourBeatStoryFeed,
  getFeedEmptyState,
  getFilterCounts,
  getStoryFilterOption,
  normalizeStoryFilter,
} from './storiesFeedView'
import {
  canonicalStoriesPageEnabled,
  getCanonicalStoryFeed,
  hasUsableCanonicalStoriesFeed,
} from './storiesCanonicalFeedView'

// BaseballOS Stories — the browseable bullpen intelligence feed. This page
// renders backend-authored four-beat stories as the product feed.
export default function Stories() {
  const dash = useFetch(getBullpenDashboard)

  return (
    <StoriesView
      dashboard={dash.data}
      loading={dash.loading}
      error={dash.error}
      staleWithError={dash.staleWithError}
      onRetry={dash.refetch}
    />
  )
}

export function StoriesView({
  dashboard,
  loading = false,
  error = null,
  staleWithError = false,
  canonicalStoriesEnabled = canonicalStoriesPageEnabled(),
  onRetry,
  initialFilter = 'all',
}) {
  const [filter, setFilter] = useState(initialFilter)
  const masthead = getMastheadView(dashboard)
  // Canonical backend stories power the feed only when the flag is on and the
  // payload is well-formed; otherwise Stories keeps its legacy Four-Beat feed.
  const useCanonicalStories = canonicalStoriesEnabled && hasUsableCanonicalStoriesFeed(dashboard)
  const feed = useCanonicalStories ? getCanonicalStoryFeed(dashboard) : getFourBeatStoryFeed(dashboard)
  const counts = getFilterCounts(feed.items)
  const activeFilter = normalizeStoryFilter(filter)
  const activeOption = getStoryFilterOption(activeFilter)
  const activeCount = counts[activeFilter] ?? 0
  const activeLabel = getActiveStoryFilterLabel(activeFilter, activeCount)
  const visible = filterStoryFeed(feed.items, activeFilter)

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
              Descriptive bullpen notes.
            </span>
          </div>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
          What else BaseballOS is seeing today — team observations, trend notes, and bullpen watch items beyond the morning briefing.
        </p>
      </header>

      {loading && !dashboard ? (
        <LoadingPane message="Gathering today's bullpen stories..." />
      ) : error && !dashboard ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <>
          {staleWithError && (
            <StaleDataNotice
              message="Stories are based on the last loaded dashboard snapshot because the latest refresh failed."
              onRetry={onRetry}
            />
          )}

          <FeedScope
            feed={feed}
            counts={counts}
          />

          <section className="mb-8" aria-label="Story feed">
            <SectionHeading
              title="The Story Feed"
              subtitle="Every storyline BaseballOS is carrying today. Pick a lane or read it all."
            />

            <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Story filters">
              {STORY_FILTERS.map(option => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setFilter(option.key)}
                  aria-pressed={activeFilter === option.key}
                  aria-label={`${option.label}: ${option.description}`}
                  title={option.description}
                  className={`rounded border px-3 py-1.5 font-mono text-xs transition-all ${
                    activeFilter === option.key
                      ? 'border-amber/40 bg-amber/10 text-amber'
                      : 'border-dirt text-chalk400 hover:border-chalk400'
                  }`}
                >
                  {option.label}
                  <span className="ml-1.5 opacity-70">({counts[option.key] ?? 0})</span>
                </button>
              ))}
            </div>

            <div className="mb-4 border-y border-dirt/70 py-3">
              <p className="font-mono text-[11px] uppercase tracking-widest text-amber/80">{activeLabel}</p>
              <p className="mt-1 max-w-3xl text-sm leading-relaxed text-chalk400">{activeOption.description}</p>
            </div>

            {visible.length === 0 ? (
              <StoryFeedEmptyState
                state={getFeedEmptyState(activeFilter)}
                onReset={() => setFilter(DEFAULT_STORY_FILTER)}
              />
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {visible.map((story, index) => (
                  <FeedStoryCard key={`${story.kicker}-${story.teamId ?? 'league'}-${index}`} story={story} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

function FeedScope({ feed, counts }) {
  const lanes = [
    { key: 'stressed', label: 'Pressure', tone: 'stress' },
    { key: 'watch', label: 'Watch', tone: 'watch' },
    { key: 'rested', label: 'Rest', tone: 'rest' },
    { key: 'league', label: 'League', tone: 'neutral' },
  ]

  return (
    <section className="mb-6 border border-dirt bg-dugout p-4 sm:p-5" aria-label="Stories scope">
      <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
        Beyond Today
      </div>
      <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-3xl leading-none tracking-wide text-chalk100">
            What Else BaseballOS Is Seeing
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
            {feed.hasStories
              ? `${feed.items.length} bullpen storylines in play today, from single pens to the league picture.`
              : feed.fallback}
          </p>
        </div>
        <Link
          to="/"
          className="rounded border border-dirt bg-field/60 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
        >
          Back to Today →
        </Link>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {lanes.map(lane => {
          const tone = homeTone(lane.tone)
          return (
            <span
              key={lane.key}
              className="inline-flex items-center gap-2 rounded border px-2.5 py-1 font-mono text-[11px]"
              style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
              {lane.label}
              <span className="text-chalk100">{counts[lane.key] ?? 0}</span>
            </span>
          )
        })}
      </div>
    </section>
  )
}

function StoryFeedEmptyState({ state, onReset }) {
  return (
    <div className="card p-5 text-sm text-chalk400">
      <div className="max-w-2xl">
        <p className="text-base font-semibold text-chalk100">{state.title}</p>
        <p className="mt-2 leading-relaxed">{state.body}</p>
        <button
          type="button"
          data-reset-filter={state.resetFilter}
          onClick={onReset}
          className="mt-4 inline-flex items-center rounded border border-amber/30 bg-amber/10 px-3 py-1.5 font-mono text-xs text-amber transition-colors hover:border-amber/50 hover:bg-amber/15"
        >
          Show All Stories <span className="ml-1" aria-hidden="true">→</span>
        </button>
      </div>
    </div>
  )
}

// A feed entry with the club named when the story belongs to one.
function FeedStoryCard({ story }) {
  const tone = homeTone(story.tone)
  const hasDestination = Boolean(story.href)
  const hasTeam = story.teamId != null && Boolean(story.abbr)
  const team = {
    team_id: story.teamId,
    team_name: story.teamName,
    team_abbreviation: story.abbr,
  }

  const inner = (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="h-1 w-8 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
            {story.teamId != null
              ? formatTeamLabel({ team_abbreviation: story.abbr, team_name: story.teamName }, 'Around the league')
              : 'Around the league'}
          </span>
          {hasTeam && (
            <TeamShareButton
              team={team}
              className="pointer-events-auto"
            />
          )}
        </div>
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

      <StoryNarrativeBody text={story.narrative || story.body} />
      <StoryDisclosureNote note={story.disclosureNote || story.disclosure_note} />

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
    <article
      className="card group relative flex flex-col p-5 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5"
    >
      <Link
        to={story.href}
        aria-label={story.cta || 'Open the full picture'}
        className="absolute inset-0 z-10"
      />
      <div className="relative z-20 flex flex-1 flex-col pointer-events-none">
        {inner}
      </div>
    </article>
  )
}

function StoryNarrativeBody({ text }) {
  const paragraphs = typeof text === 'string'
    ? text.split(/\n{2,}/).map(paragraph => paragraph.trim()).filter(Boolean)
    : []
  if (paragraphs.length === 0) return null

  return (
    <div className="mt-3 flex-1 space-y-2">
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="text-xs leading-relaxed text-chalk400">{paragraph}</p>
      ))}
    </div>
  )
}

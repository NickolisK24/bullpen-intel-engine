import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import { createServer } from 'vite'

// storiesFeedView.js now holds only the shared browse/filter utilities the
// canonical Stories page renders with — the legacy Four-Beat feed was retired in
// Phase 5D. These tests cover those utilities and guard that Stories stays
// canonical-only.

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const {
  DEFAULT_STORY_FILTER,
  STORY_FILTERS,
  filterStoryFeed,
  getActiveStoryFilterLabel,
  getFeedEmptyState,
  getFilterCounts,
  getStoryFilterOption,
  normalizeStoryFilter,
} = await server.ssrLoadModule('/src/components/stories/storiesFeedView.js')

const readSrc = (rel) => readFileSync(new URL(`../src/${rel}`, import.meta.url), 'utf8')

// Synthetic feed cards in the shape the canonical adapter produces and the
// filters read: one `category` lane per card.
const feedItems = [
  { category: 'stressed', teamId: 1 },
  { category: 'stressed', teamId: 2 },
  { category: 'rested', teamId: 3 },
  { category: 'watch', teamId: 4 },
  { category: 'league', teamId: null },
]

test('filter metadata carries concise descriptions and active labels', () => {
  for (const { key, description } of STORY_FILTERS) {
    const option = getStoryFilterOption(key)
    assert.equal(option.description, description)
    assert.equal(option.description.split('.').filter(Boolean).length, 1)
    assert.ok(getActiveStoryFilterLabel(key, 2).includes('(2)'))
  }
  assert.equal(normalizeStoryFilter('unknown-lane'), DEFAULT_STORY_FILTER)
  assert.equal(getFeedEmptyState('unknown-lane').resetFilter, DEFAULT_STORY_FILTER)
})

test('getFilterCounts tallies each lane and the all-count is the total', () => {
  const counts = getFilterCounts(feedItems)
  assert.equal(counts.all, 5)
  assert.equal(counts.stressed, 2)
  assert.equal(counts.rested, 1)
  assert.equal(counts.watch, 1)
  assert.equal(counts.league, 1)
  // Robust to non-arrays.
  assert.equal(getFilterCounts(null).all, 0)
})

test('filterStoryFeed slices by lane; the default lane returns everything', () => {
  assert.equal(filterStoryFeed(feedItems, DEFAULT_STORY_FILTER).length, 5)
  assert.equal(filterStoryFeed(feedItems, 'stressed').length, 2)
  assert.equal(filterStoryFeed(feedItems, 'league').length, 1)
  assert.deepEqual(filterStoryFeed(feedItems, 'rested').map(item => item.teamId), [3])
  // An unknown filter normalizes to All (everything).
  assert.equal(filterStoryFeed(feedItems, 'unknown-lane').length, 5)
})

test('each filter lane carries an empty-state title and resets to All', () => {
  for (const { key } of STORY_FILTERS) {
    const empty = getFeedEmptyState(key)
    assert.equal(empty.filter, key)
    assert.ok(empty.title)
    assert.equal(empty.resetFilter, DEFAULT_STORY_FILTER)
  }
})

test('Stories is canonical-only: no Four-Beat feed import or legacy story-path switch', () => {
  const storiesSource = readSrc('components/stories/Stories.jsx')
  const feedSource = readSrc('components/stories/storiesFeedView.js')
  // Stories.jsx renders only the canonical feed.
  assert.equal(storiesSource.includes('getFourBeatStoryFeed'), false)
  assert.equal(storiesSource.includes('four_beat'), false)
  assert.equal(storiesSource.includes('canonicalStoriesPageEnabled'), false)
  assert.equal(storiesSource.includes('getBullpenObservations'), false)
  assert.ok(storiesSource.includes('getCanonicalStoryFeed'))
  // The shared view no longer carries any Four-Beat code.
  assert.equal(feedSource.includes('getFourBeatStoryFeed'), false)
  assert.equal(feedSource.includes('FOUR_BEAT_STORIES_FALLBACK'), false)
  assert.equal(feedSource.includes('backend_four_beat'), false)
})

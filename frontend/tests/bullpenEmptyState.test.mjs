import assert from 'node:assert/strict'
import test from 'node:test'

import { getBullpenEmptyState } from '../src/components/bullpen/emptyState.js'

test('explains when freshness excludes available workload data', () => {
  const state = getBullpenEmptyState({
    allRowsCount: 0,
    visibleRowsCount: 0,
    includeStale: false,
    meta: {
      total_game_logs: 20,
      total_scored_pitchers: 2,
      filtered_scored_pitchers: 2,
      fresh_filtered_pitchers: 0,
      stale_filtered_pitchers: 2,
    },
  })

  assert.equal(state.title, 'No current pitchers match the freshness filter.')
  assert.match(state.subtitle, /Show inactive pitchers/)
  assert.doesNotMatch(state.subtitle, /seed\.py/)
})

test('keeps setup guidance for a genuinely empty database', () => {
  const state = getBullpenEmptyState({
    allRowsCount: 0,
    visibleRowsCount: 0,
    meta: {
      total_game_logs: 0,
      total_scored_pitchers: 0,
      filtered_scored_pitchers: 0,
      fresh_filtered_pitchers: 0,
      stale_filtered_pitchers: 0,
    },
  })

  assert.equal(state.title, 'No pitcher workload data found')
  assert.match(state.subtitle, /python seed\.py/)
})

test('reports visible filter misses separately from data availability', () => {
  const riskState = getBullpenEmptyState({
    allRowsCount: 5,
    visibleRowsCount: 0,
    riskFilter: 'CRITICAL',
    meta: { total_game_logs: 10, total_scored_pitchers: 5 },
  })
  const searchState = getBullpenEmptyState({
    allRowsCount: 5,
    visibleRowsCount: 0,
    searchTerm: 'rivera',
    meta: { total_game_logs: 10, total_scored_pitchers: 5 },
  })

  assert.match(riskState.title, /critical risk/)
  assert.equal(searchState.title, 'No pitchers match your search.')
})

test('reports availability filter misses without setup guidance', () => {
  const state = getBullpenEmptyState({
    allRowsCount: 5,
    visibleRowsCount: 0,
    availabilityFilter: 'Unavailable',
    meta: { total_game_logs: 10, total_scored_pitchers: 5 },
  })

  assert.equal(state.title, 'No pitchers match the Unavailable availability filter.')
  assert.match(state.subtitle, /availability status/)
  assert.doesNotMatch(state.subtitle, /seed\.py/)
})

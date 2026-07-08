import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('Pitcher Detail source has no score-first chart or threshold framing', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )

  const availabilityIndex = source.indexOf('<AvailabilitySummary')
  const workloadFactsIndex = source.indexOf('Recent Workload Snapshot')
  const recentWorkIndex = source.indexOf('<RecentWorkPanel pitcherId={pitcherId} />')

  assert.notEqual(availabilityIndex, -1)
  assert.notEqual(workloadFactsIndex, -1)
  assert.notEqual(recentWorkIndex, -1)
  assert.ok(availabilityIndex < workloadFactsIndex)
  assert.ok(workloadFactsIndex < recentWorkIndex)

  for (const forbidden of [
    'Workload Index',
    '0-100',
    'RadarChart',
    'ReferenceLine',
    'Workload Profile',
    'Workload Trend',
    'FATIGUE_FACTORS',
    'RISK_BLURB',
    '<RiskBadge',
    '<FatigueBar',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('All Pitchers source uses workload units instead of score or risk leaderboard behavior', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url),
    'utf8',
  )

  for (const required of [
    "useState('pitches')",
    "if (sortBy === 'pitches') return b.pitches_last_7_days - a.pitches_last_7_days",
    'P/7d',
    'Rest',
    'App/7d',
    '<AvailabilityBadge availability={row.availability} showDataState />',
  ]) {
    assert.ok(source.includes(required), required)
  }

  for (const forbidden of [
    "useState('score')",
    "sortBy === 'score'",
    "setSortBy('score')",
    '<RiskBadge',
    '<FatigueBar',
    'riskFilter',
    'RISK_FILTERS',
    'raw_score',
    'Recent Load',
    '>Risk<',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('Team board pitcher cards do not expose the 0-100 workload index', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/BullpenBoardView.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('Workload Read'))
  for (const forbidden of [
    'Recent workload index',
    '0-100',
    'Recent Load',
    'view.fatigueScore',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

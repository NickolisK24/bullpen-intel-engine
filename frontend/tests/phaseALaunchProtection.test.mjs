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

test('Reliever Finder source shows honest workload facts with a neutral default order, not a score or leaderboard', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url),
    'utf8',
  )

  for (const required of [
    // Neutral default order (name A–Z) instead of a workload-descending open.
    'useState(DEFAULT_FINDER_SORT)',
    // The pitches and rest orderings stay user-selectable, keyboard-reachable
    // sorts of honest baseball facts.
    "sortHeaderProps('pitches')",
    "sortHeaderProps('rest')",
    // Reader-clear column labels replace the cramped P/7d and App/7d.
    'Pitches (7d)',
    'Appearances (7d)',
    'Rest',
    '<AvailabilityBadge availability={row.availability} showDataState />',
  ]) {
    assert.ok(source.includes(required), required)
  }

  for (const forbidden of [
    // The finder must not open ranked by workload.
    "useState('pitches')",
    "useState('score')",
    "sortBy === 'score'",
    "setSortBy('score')",
    // The retired cramped column abbreviations must not return.
    'P/7d',
    'App/7d',
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

test('Reliever Finder ordering uses honest workload facts, never a composite metric', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/relieverFinderView.js', import.meta.url),
    'utf8',
  )

  // The explicit orderings sort real pitch and rest facts; the default is name.
  assert.ok(source.includes('pitches_last_7_days'))
  assert.ok(source.includes('days_since_last_appearance'))
  assert.ok(source.includes("NAME: 'name'"))
  assert.ok(source.includes('DEFAULT_FINDER_SORT = FINDER_SORTS.NAME'))

  for (const forbidden of ['raw_score', 'fatigueScore', 'compositeScore', 'RISK_', 'grade']) {
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

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  filterRowsByAvailability,
  formatConfidence,
  getAvailabilityBadgeView,
  getAvailabilityFilterCounts,
  getAvailabilitySummary,
  getDataStateView,
} from '../src/components/bullpen/availabilityView.js'

const rows = [
  { pitcher_id: 1, availability: { availability_status: 'Available' } },
  { pitcher_id: 2, availability: { availability_status: 'Monitor' } },
  { pitcher_id: 3, availability: { availability_status: 'Limited' } },
  { pitcher_id: 4, availability: { availability_status: 'Avoid' } },
  { pitcher_id: 5, availability: { availability_status: 'Unavailable' } },
]

test('builds availability badge labels from backend status values', () => {
  const badge = getAvailabilityBadgeView({ availability_status: 'Limited' })

  assert.equal(badge.label, 'Limited')
  assert.equal(badge.status, 'Limited')
  assert.match(badge.tone, /workload/i)
})

test('filters rows by backend availability status without reclassifying', () => {
  const limited = filterRowsByAvailability(rows, 'Limited')
  const all = filterRowsByAvailability(rows, 'ALL')

  assert.deepEqual(limited.map(row => row.pitcher_id), [3])
  assert.equal(all.length, rows.length)
})

test('counts availability filter options from returned rows', () => {
  const counts = getAvailabilityFilterCounts(rows)

  assert.equal(counts.ALL, 5)
  assert.equal(counts.Available, 1)
  assert.equal(counts.Monitor, 1)
  assert.equal(counts.Limited, 1)
  assert.equal(counts.Avoid, 1)
  assert.equal(counts.Unavailable, 1)
})

test('formats confidence values for display', () => {
  assert.equal(formatConfidence('high'), 'High')
  assert.equal(formatConfidence('medium'), 'Medium')
  assert.equal(formatConfidence('low'), 'Low')
  assert.equal(formatConfidence(null), 'Unknown')
})

test('describes stale data state clearly', () => {
  const stale = getDataStateView('stale')

  assert.equal(stale.label, 'Stale')
  assert.match(stale.message, /active freshness window/i)
})

test('preserves explanation reasons and limitations from backend output', () => {
  const summary = getAvailabilitySummary({
    availability_status: 'Avoid',
    confidence: 'low',
    data_state: 'stale',
    reasons: ['42 pitches yesterday', '4 appearances in 5 days'],
    limitations: ['No team-reported availability data available'],
  })

  assert.equal(summary.label, 'Avoid')
  assert.equal(summary.confidenceLabel, 'Low')
  assert.equal(summary.dataStateView.label, 'Stale')
  assert.deepEqual(summary.reasons, ['42 pitches yesterday', '4 appearances in 5 days'])
  assert.deepEqual(summary.limitations, ['No team-reported availability data available'])
})

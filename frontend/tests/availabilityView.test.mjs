import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AVAILABILITY_FILTERS,
  filterRowsByAvailability,
  formatConfidence,
  getAvailabilityBadgeView,
  getAvailabilityFilterCounts,
  getAvailabilitySummary,
  getDataStateView,
} from '../src/components/bullpen/availabilityView.js'
import { availabilityFixtureRows } from './fixtures/availabilityStatusFixtures.mjs'

const statuses = AVAILABILITY_FILTERS.filter(status => status !== 'ALL')

test('builds availability badge labels from every backend status value', () => {
  for (const row of availabilityFixtureRows) {
    const status = row.availability.availability_status
    const badge = getAvailabilityBadgeView(row.availability)

    assert.equal(badge.label, status)
    assert.equal(badge.status, status)
    assert.match(badge.tone, /workload|signals|rules/i)
  }
})

test('filters rows by every backend availability status without reclassifying', () => {
  for (const status of statuses) {
    const filtered = filterRowsByAvailability(availabilityFixtureRows, status)

    assert.equal(filtered.length, 1)
    assert.equal(filtered[0].availability.availability_status, status)
  }

  const all = filterRowsByAvailability(availabilityFixtureRows, 'ALL')
  assert.equal(all.length, availabilityFixtureRows.length)
})

test('counts availability filter options from returned rows', () => {
  const counts = getAvailabilityFilterCounts(availabilityFixtureRows)

  assert.equal(counts.ALL, 5)
  assert.equal(counts.Available, 1)
  assert.equal(counts.Monitor, 1)
  assert.equal(counts.Limited, 1)
  assert.equal(counts.Avoid, 1)
  assert.equal(counts.Unavailable, 1)
})

test('formats fixture confidence values for display', () => {
  for (const row of availabilityFixtureRows) {
    assert.match(formatConfidence(row.availability.confidence), /^(Strong Read|Limited Read|Unclear Read)$/)
  }
  assert.equal(formatConfidence(null), 'Unknown Read')
})

test('describes stale data state clearly for Monitor fixture', () => {
  const stale = getDataStateView('stale')
  const monitor = availabilityFixtureRows.find(row => row.availability.availability_status === 'Monitor')

  assert.equal(stale.label, 'Recent Usage Unknown')
  assert.match(stale.message, /active freshness window/i)
  assert.equal(getDataStateView(monitor.availability.data_state).label, 'Recent Usage Unknown')
})

test('preserves explanation reasons and limitations from fixture backend output', () => {
  for (const row of availabilityFixtureRows) {
    const summary = getAvailabilitySummary(row.availability)

    assert.equal(summary.label, row.availability.availability_status)
    assert.equal(summary.confidenceLabel, formatConfidence(row.availability.confidence))
    assert.equal(summary.dataStateView.label, getDataStateView(row.availability.data_state).label)
    assert.deepEqual(summary.reasons, row.availability.reasons)
    assert.deepEqual(summary.limitations, row.availability.limitations)
    assert.ok(summary.reasons.length > 0)
    assert.ok(summary.limitations.length > 0)
  }
})

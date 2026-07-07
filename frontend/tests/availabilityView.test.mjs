import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AVAILABILITY_FILTERS,
  filterRowsByAvailability,
  formatConfidence,
  getAvailabilityBadgeView,
  getAvailabilityFilterCounts,
  getAvailabilitySummary,
  getAvailabilityStatusLabel,
  getDataStateView,
} from '../src/components/bullpen/availabilityView.js'
import { availabilityFixtureRows } from './fixtures/availabilityStatusFixtures.mjs'

const statuses = AVAILABILITY_FILTERS.filter(status => status !== 'ALL')

test('builds availability badge labels from every backend status value', () => {
  for (const row of availabilityFixtureRows) {
    const status = row.availability.availability_status
    const badge = getAvailabilityBadgeView(row.availability)

    assert.equal(badge.label, getAvailabilityStatusLabel(status))
    assert.equal(badge.status, status)
    assert.match(badge.tone, /recent usage|recent work|workload|signals|rules/i)
  }
})

test('filters rows by public availability status while preserving raw backend values', () => {
  for (const status of statuses) {
    const filtered = filterRowsByAvailability(availabilityFixtureRows, status)

    if (status === 'Unavailable') {
      assert.equal(filtered.length, 2)
      assert.deepEqual(filtered.map(row => row.availability.availability_status), ['Avoid', 'Unavailable'])
    } else {
      assert.equal(filtered.length, 1)
      assert.equal(filtered[0].availability.availability_status, status)
    }
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
  assert.equal(counts.Unavailable, 2)
  assert.equal(counts.Avoid, undefined)
})

test('raw Avoid status displays as public Unavailable copy', () => {
  const rawAvoid = availabilityFixtureRows.find(row => row.availability.availability_status === 'Avoid')
  const badge = getAvailabilityBadgeView(rawAvoid.availability)
  const summary = getAvailabilitySummary(rawAvoid.availability)

  assert.equal(getAvailabilityStatusLabel('Avoid'), 'Unavailable')
  assert.equal(badge.status, 'Avoid')
  assert.equal(badge.label, 'Unavailable')
  assert.equal(summary.label, 'Unavailable')
})

test('formats fixture confidence values for display', () => {
  for (const row of availabilityFixtureRows) {
    assert.match(formatConfidence(row.availability.confidence), /^(Strong Read|Partial Read|Unclear Read)$/)
  }
  assert.equal(formatConfidence(null), 'Unknown Read')
})

test('describes stale data state clearly for Monitor fixture', () => {
  const stale = getDataStateView('stale')
  const monitor = availabilityFixtureRows.find(row => row.availability.availability_status === 'Monitor')

  assert.equal(stale.label, 'Outside Freshness Window')
  assert.match(stale.message, /latest appearance is older than the active freshness window/i)
  assert.doesNotMatch(stale.message, /fetch failed|no workload history/i)
  assert.equal(getDataStateView(monitor.availability.data_state).label, 'Outside Freshness Window')
})

test('distinguishes missing and failed workload states from stale usage', () => {
  const missing = getDataStateView('missing')
  const failed = getDataStateView('failed')

  assert.equal(missing.label, 'No Workload Record')
  assert.match(missing.message, /No recent workload history/i)
  assert.doesNotMatch(missing.message, /fetch failed|freshness window/i)
  assert.equal(failed.label, 'Fetch Failed')
  assert.match(failed.message, /workload fetch failed/i)
  assert.doesNotMatch(failed.message, /older than the active freshness window|No workload history/i)
})

test('preserves explanation reasons and limitations from fixture backend output', () => {
  for (const row of availabilityFixtureRows) {
    const summary = getAvailabilitySummary(row.availability)

    assert.equal(summary.label, getAvailabilityStatusLabel(row.availability.availability_status))
    assert.equal(summary.confidenceLabel, formatConfidence(row.availability.confidence))
    assert.equal(summary.dataStateView.label, getDataStateView(row.availability.data_state).label)
    assert.deepEqual(summary.reasons, row.availability.reasons)
    assert.deepEqual(summary.limitations, row.availability.limitations)
    assert.ok(summary.reasons.length > 0)
    assert.ok(summary.limitations.length > 0)
  }
})

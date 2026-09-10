import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getGovernedWorkloadFacts,
  getRestStatusView,
  getWorkloadColumns,
  getWorkloadTrendView,
  getWorkloadWindowRows,
} from '../src/components/bullpen/board/teamBoardWorkloadView.js'

const EMPTY_WORKLOAD_FACTS = {
  days_since_last_appearance: null,
  appearances_last_7: null,
  pitches_last_7_days: null,
  back_to_back: null,
}

test('governed workload facts accept only the exact board contract fields', () => {
  const facts = getGovernedWorkloadFacts({
    workload_facts: {
      days_since_last_appearance: 0,
      appearances_last_7: 3,
      pitches_last_7_days: 42,
      back_to_back: true,
      extra_field: 99,
    },
    workloadFacts: {
      days_since_last_appearance: 8,
    },
  })

  assert.deepEqual(facts, {
    days_since_last_appearance: 0,
    appearances_last_7: 3,
    pitches_last_7_days: 42,
    back_to_back: true,
  })
  assert.deepEqual(Object.keys(facts), Object.keys(EMPTY_WORKLOAD_FACTS))
})

test('governed workload facts fail malformed counts closed and preserve boolean values', () => {
  for (const [value, expected] of [
    [-1, null],
    ['2', null],
    [null, null],
    [2, 2],
  ]) {
    assert.equal(getGovernedWorkloadFacts({
      workload_facts: { appearances_last_7: value },
    }).appearances_last_7, expected)
  }

  for (const [value, expected] of [
    [true, true],
    [false, false],
    [null, null],
    [1, null],
  ]) {
    assert.equal(getGovernedWorkloadFacts({
      workload_facts: { back_to_back: value },
    }).back_to_back, expected)
  }

  assert.deepEqual(getGovernedWorkloadFacts(null), EMPTY_WORKLOAD_FACTS)
  assert.deepEqual(getGovernedWorkloadFacts({ workloadFacts: {} }), EMPTY_WORKLOAD_FACTS)
})

test('Rest Status accepts coherent backend-authored counts and summary', () => {
  assert.deepEqual(getRestStatusView({
    available: true,
    active_arm_count: 6,
    rested_arm_count: 3,
    worked_yesterday_count: 2,
    back_to_back_count: 1,
    summary: '  Three rested options remain.  ',
    reason_code: 'not_reader_copy',
  }), {
    available: true,
    active_arm_count: 6,
    rested_arm_count: 3,
    worked_yesterday_count: 2,
    back_to_back_count: 1,
    summary: 'Three rested options remain.',
  })
})

test('Rest Status fails malformed or incoherent reads closed without leaking reasons or counts', () => {
  for (const restStatus of [
    null,
    { available: false, active_arm_count: 6, reason_code: 'workload_evidence_incomplete' },
    { available: true, active_arm_count: -1, rested_arm_count: 0, worked_yesterday_count: 0, back_to_back_count: 0, summary: 'Invalid.' },
    { available: true, active_arm_count: '6', rested_arm_count: 3, worked_yesterday_count: 2, back_to_back_count: 1, summary: 'Invalid.' },
    { available: true, active_arm_count: 6, rested_arm_count: null, worked_yesterday_count: 2, back_to_back_count: 1, summary: 'Invalid.' },
    { available: true, active_arm_count: 2, rested_arm_count: 3, worked_yesterday_count: 0, back_to_back_count: 0, summary: 'Invalid.' },
    { available: true, active_arm_count: 6, rested_arm_count: 3, worked_yesterday_count: 2, back_to_back_count: 1 },
    { available: true, active_arm_count: 6, rested_arm_count: 3, worked_yesterday_count: 2, back_to_back_count: 1, summary: '   ' },
  ]) {
    assert.deepEqual(getRestStatusView(restStatus), { available: false })
  }
})

test('workload windows preserve published order without creating 3-day or 30-day rows', () => {
  const rows = getWorkloadWindowRows({
    windows: [
      { window_days: 14, through: '2026-08-18', relief_appearances: 8, pitches_total: null, outs_total: 24 },
      { window_days: 7, through: '2026-08-18', relief_appearances: 0, pitches_total: 0 },
      { window_days: null, through: '2026-08-18', relief_appearances: 2, pitches_total: 25 },
    ],
  })

  assert.deepEqual(rows.map(row => row.label), ['14 days', '7 days'])
  assert.equal(rows[0].pitches, null)
  assert.equal(rows[1].appearances, 0)
  assert.equal(rows[1].pitches, 0)
  assert.deepEqual(getWorkloadColumns(rows).map(column => column.key), ['appearances', 'pitches'])
  assert.equal(Object.hasOwn(rows[0], 'outs'), false)
  assert.equal(rows.some(row => row.label === '3 days' || row.label === '30 days'), false)
})

test('daily workload trend places only governed outs on an authoritative 30-day axis', () => {
  const view = getWorkloadTrendView({
    data_through: '2026-08-18',
    relief_by_date: [
      { game_date: '2026-08-18', outs_total: 6 },
      { game_date: '2026-08-16', outs_total: 0 },
    ],
  })

  assert.equal(view.available, true)
  assert.equal(view.slots.length, 30)
  assert.equal(view.slots[0].date, '2026-07-20')
  assert.equal(view.slots.at(-1).date, '2026-08-18')
  assert.deepEqual(view.slots.at(-1), { date: '2026-08-18', published: true, outs: 6 })
  assert.deepEqual(view.slots.find(slot => slot.date === '2026-08-16'), { date: '2026-08-16', published: true, outs: 0 })
  assert.deepEqual(view.slots.find(slot => slot.date === '2026-08-17'), { date: '2026-08-17', published: false, outs: null })
  assert.equal(view.publishedDayCount, 2)
})

test('daily workload trend stays absent without valid governed date groups', () => {
  for (const reliefWork of [
    null,
    { data_through: '2026-08-18', relief_by_date: [] },
    { data_through: '2026-08-18', relief_by_date: [{ game_date: '2026-08-18', outs_total: null }] },
    { data_through: 'not-a-date', relief_by_date: [{ game_date: '2026-08-18', outs_total: 6 }] },
    { data_through: '2026-08-18', relief_by_date: [{ game_date: '2026-07-01', outs_total: 6 }] },
  ]) {
    assert.deepEqual(getWorkloadTrendView(reliefWork), { available: false })
  }
})

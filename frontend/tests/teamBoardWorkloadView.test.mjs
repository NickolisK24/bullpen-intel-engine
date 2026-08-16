import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getGovernedWorkloadFacts,
  getRestStatusView,
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

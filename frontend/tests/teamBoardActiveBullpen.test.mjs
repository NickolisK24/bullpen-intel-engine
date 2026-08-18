import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

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
  default: TeamBoardActiveBullpen,
  ActiveBullpenSkeleton,
  getActiveBullpenRows,
} = await server.ssrLoadModule('/src/components/bullpen/board/TeamBoardActiveBullpen.jsx')

const text = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

function arm(overrides = {}) {
  return {
    pitcher_id: 22,
    name: 'Christopher Longname-Example',
    public_role_read: { key: 'bridge_arm', label: 'Backend Setup Phrase' },
    public_labels: {
      role: { key: 'bridge_arm', label: 'Backend Setup Phrase' },
      read: { key: 'watch_arm', label: 'Backend Watch Phrase' },
    },
    availability: { label: 'On Watch' },
    last_appearance: { date: '2026-08-15', pitches: 18 },
    workload: {
      days_since_last_appearance: 1,
      appearances_last_7: 2,
      pitches_last_7_days: 34,
      back_to_back: true,
    },
    roster_status: { status: 'active' },
    visibility: { is_visible_by_default: true },
    ...overrides,
  }
}

function read(overrides = {}) {
  return {
    team: { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
    activeBullpen: {
      population_basis: 'current_scored_bullpen_eligible_pitchers',
      arm_count: 2,
      arms: [
        arm(),
        arm({
          pitcher_id: 11,
          name: 'Second Arm',
          public_role_read: { key: 'limited_read', label: 'Backend Role Phrase' },
          public_labels: {
            role: { key: 'limited_read', label: 'Backend Role Phrase' },
            read: { key: 'unknown-new-key', label: 'Backend Limited Phrase' },
          },
          last_appearance: { date: '2026-08-16', pitches: 0 },
          workload: {
            days_since_last_appearance: 0,
            appearances_last_7: 0,
            pitches_last_7_days: null,
            back_to_back: false,
          },
        }),
      ],
    },
    sectionStatus: {
      active_bullpen: { status: 'available', reason_code: null, limitations: [] },
    },
    ...overrides,
  }
}

const render = props => renderToStaticMarkup(React.createElement(TeamBoardActiveBullpen, props))

test('renders the v2 arm population exactly once and preserves backend order', () => {
  const rows = getActiveBullpenRows(read().activeBullpen)
  assert.deepEqual(rows.map(row => row.pitcherId), [22, 11])

  const html = render({ read: read(), onSelectPitcher: () => {} })
  assert.equal((html.match(/class="active-arm-row"/g) || []).length, 2)
  assert.ok(html.indexOf('Christopher Longname-Example') < html.indexOf('Second Arm'))
  assert.equal(html.includes('BullpenBoardView'), false)
})

test('renders backend-owned read and role labels verbatim with color-independent text', () => {
  const html = render({ read: read() })
  assert.ok(text(html).includes('Backend Watch Phrase'))
  assert.ok(text(html).includes('Backend Setup Phrase'))
  assert.ok(text(html).includes('Backend Limited Phrase'))
  assert.ok(text(html).includes('Backend Role Phrase'))
  assert.match(html, /semantic-label--watch/)
  assert.match(html, /semantic-label--neutral/)
})

test('renders only authorized workload facts and preserves legitimate zero', () => {
  const html = render({ read: read() })
  const visible = text(html)

  for (const expected of ['1 day ago', '18 pitches', '34', 'Back-to-back', 'Today', '0 pitches']) {
    assert.ok(visible.includes(expected), expected)
  }
  assert.equal((visible.match(/7D Pitches/g) || []).length, 1)
  assert.equal(visible.includes('3-in-4'), false)
  assert.equal(visible.includes('4-in-6'), false)
  assert.equal(visible.includes('fatigue'), false)
})

test('missing facts are omitted rather than converted to zero', () => {
  const rows = getActiveBullpenRows({ arms: [arm({
    last_appearance: null,
    workload: {
      days_since_last_appearance: null,
      appearances_last_7: null,
      pitches_last_7_days: null,
      back_to_back: null,
    },
  })] })

  assert.deepEqual(rows[0].facts, [])
  const html = render({ read: read({
    activeBullpen: { population_basis: 'basis', arm_count: 1, arms: [arm({ last_appearance: null, workload: {} })] },
  }) })
  assert.equal(text(html).includes('7D Pitches 0'), false)
  assert.equal(text(html).includes('Last Game 0'), false)
})

test('multi-day pattern is used only for the supplied true back-to-back fact', () => {
  const rows = getActiveBullpenRows(read().activeBullpen)
  assert.deepEqual(rows[0].facts.at(-1), { label: 'Pattern', value: 'Back-to-back' })
  assert.equal(rows[1].facts.some(fact => fact.label === 'Pattern'), false)
})

test('loading uses the row-oriented ActiveArmRow skeleton', () => {
  const html = renderToStaticMarkup(React.createElement(ActiveBullpenSkeleton))
  assert.ok(html.includes('data-testid="active-bullpen-skeleton"'))
  assert.ok(html.includes('aria-busy="true"'))
  assert.equal((html.match(/aria-label="Loading reliever record"/g) || []).length, 3)
})

test('partial content keeps available arms and shows one scoped public limitation', () => {
  const html = render({ read: read({
    sectionStatus: {
      active_bullpen: {
        status: 'partial',
        reason_code: 'current_population_counts_withheld',
        limitations: ['Current roster evidence is incomplete.', 'Second limitation is not repeated.'],
      },
    },
  }) })

  assert.ok(text(html).includes('Christopher Longname-Example'))
  assert.ok(text(html).includes('Active Bullpen is partially available'))
  assert.ok(text(html).includes('Current roster evidence is incomplete.'))
  assert.equal(text(html).includes('Second limitation is not repeated.'), false)
  assert.equal(text(html).includes('current_population_counts_withheld'), false)
})

test('unavailable, error, and legitimately empty populations remain distinct', () => {
  const unavailable = render({ read: read({
    activeBullpen: { population_basis: 'basis', arm_count: null, arms: [] },
    sectionStatus: { active_bullpen: { status: 'unavailable', limitations: [] } },
  }) })
  const failed = render({ read: null, error: new Error('transport detail'), onRetry: () => {} })
  const empty = render({ read: read({ activeBullpen: { population_basis: 'basis', arm_count: 0, arms: [] } }) })

  assert.ok(text(unavailable).includes('The active bullpen population is unavailable.'))
  assert.ok(text(failed).includes('The current Active Bullpen could not be loaded.'))
  assert.equal(text(failed).includes('transport detail'), false)
  assert.match(failed, /<button[^>]*>Try again<\/button>/)
  assert.ok(text(empty).includes('The current active-bullpen population is empty.'))
})

test('pitcher handoff is an explicit keyboard-accessible action using the existing callback', async () => {
  const html = render({ read: read(), onSelectPitcher: () => {} })
  assert.match(html, /<button[^>]*aria-label="Open pitcher context for Christopher Longname-Example"/)
  assert.ok(html.includes('min-h-11'))

  const source = await readFile(
    new URL('../src/components/bullpen/board/TeamBoardActiveBullpen.jsx', import.meta.url),
    'utf8',
  )
  assert.ok(source.includes('onSelectPitcher(row.pitcherId)'))
  assert.equal(source.includes('onClick={() => onSelectPitcher'), false)
})

test('production reuses one v2 request and retires only the grouped Team Board roster UI', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )
  assert.equal((source.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(source.includes('<TeamBoardAnswerBlock'))
  assert.ok(source.includes('<TeamBoardActiveBullpen'))
  assert.equal(source.includes('<BullpenBoardView'), false)
  assert.equal(source.includes('showUnavailable'), false)
  assert.equal(source.includes('include_stale'), false)
  for (const legacySection of ['<TeamReliefWorkPanel']) {
    assert.ok(source.includes(legacySection), legacySection)
  }
  assert.ok(source.includes('<TeamBoardRecentUsage'))
  assert.ok(source.includes('<TeamBoardRestStatus'))
  assert.ok(source.includes('<TeamBoardWorkloadOverview'))
})

test('the migrated section contains no sorting, ranking, new workload windows, or Why accordion', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/TeamBoardActiveBullpen.jsx', import.meta.url),
    'utf8',
  )
  for (const forbidden of [
    '.sort(', 'fatigue_score', 'workload_score', '3_in_4', '4_in_6',
    'appearances_last_5', '<Disclosure', 'Why?', 'reason_code',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

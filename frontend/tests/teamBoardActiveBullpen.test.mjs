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
            read: { key: 'limited_read', label: 'Backend Limited Phrase' },
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
  assert.equal((html.match(/class="active-arm-row active-arm-row--with-last-p"/g) || []).length, 2)
  assert.ok(html.indexOf('Christopher Longname-Example') < html.indexOf('Second Arm'))
  assert.equal(html.includes('BullpenBoardView'), false)
})

test('renders backend-owned read and role labels verbatim with color-independent text', () => {
  const html = render({ read: read() })
  assert.ok(text(html).includes('Backend Watch Phrase'))
  assert.ok(text(html).includes('Backend Setup Phrase'))
  assert.ok(text(html).includes('Backend Limited Phrase'))
  assert.ok(text(html).includes('Backend Role Phrase'))
  assert.match(html, /active-arm-read--watch/)
  assert.match(html, /active-arm-read__marker--dot/)
  assert.match(html, /active-arm-read__marker--ring/)
  assert.match(html, /active-arm-row__role[^>]*text-text-withheld/)
})

test('Arm Read markers use the governed neutral, caution, constrained, and withheld treatment', () => {
  const keys = [
    ['clean_option', 'neutral', 'dot'],
    ['watch_arm', 'watch', 'dot'],
    ['rest_restricted', 'limited', 'dot'],
    ['unavailable', 'withheld', 'square'],
    ['limited_read', 'withheld', 'ring'],
  ]
  const rows = getActiveBullpenRows({
    arms: keys.map(([key], index) => arm({
      pitcher_id: index + 1,
      public_labels: {
        role: { key: 'bridge_arm', label: 'Setup Arm' },
        read: { key, label: `Backend ${key}` },
      },
    })),
  })

  assert.deepEqual(rows.map(row => [row.readTone, row.readMarker]), keys.map(([, tone, marker]) => [tone, marker]))
})

test('desktop table keeps Destination sized to its label and centers every governed Read on one axis', async () => {
  const governedReads = [
    ['clean_option', 'Clean Option'],
    ['watch_arm', 'Watch Arm'],
    ['rest_restricted', 'Limited Rest'],
    ['limited_read', 'Limited Read'],
  ]
  const activeBullpen = {
    population_basis: 'current_scored_bullpen_eligible_pitchers',
    arm_count: governedReads.length,
    arms: governedReads.map(([key, label], index) => arm({
      pitcher_id: index + 1,
      public_labels: {
        role: { key: 'bridge_arm', label: 'Setup Arm' },
        read: { key, label },
      },
    })),
  }
  const html = render({ read: read({ activeBullpen }) })
  const css = await readFile(new URL('../src/index.css', import.meta.url), 'utf8')

  assert.match(html, /class="active-arm-table__read">Read</)
  assert.match(html, /class="active-arm-table__destination text-right">Destination</)
  assert.equal((html.match(/class="active-arm-row__read min-w-0"/g) || []).length, governedReads.length)
  for (const [, label] of governedReads) assert.ok(text(html).includes(label))
  assert.match(css, /minmax\(7rem, 0\.5fr\)/)
  assert.match(css, /minmax\(7rem, 0\.45fr\)/)
  assert.match(css, /\.active-arm-table__read\s*{\s*@apply text-center;/)
  assert.match(css, /\.active-arm-row__read\s*{\s*@apply items-center justify-center;/)
  assert.match(css, /\.active-arm-table__destination\s*{\s*white-space: nowrap;/)
})

test('renders only authorized workload facts and preserves legitimate zero', () => {
  const html = render({ read: read() })
  const visible = text(html)

  for (const expected of ['1d rest', '18 last P', '2 app', '34 p (7d)', 'B2B', '0d rest', '0 app', '0 last P']) {
    assert.ok(visible.includes(expected), expected)
  }
  assert.ok(visible.includes('Last P'))
  assert.equal(visible.includes('3-in-4'), false)
  assert.equal(visible.includes('4-in-6'), false)
  assert.equal(visible.includes('fatigue'), false)
})

test('missing facts use withheld values rather than converted zero', () => {
  const rows = getActiveBullpenRows({ arms: [arm({
    last_appearance: null,
    workload: {
      days_since_last_appearance: null,
      appearances_last_7: null,
      pitches_last_7_days: null,
      back_to_back: null,
    },
  })] })

  assert.equal(rows[0].daysSince, null)
  assert.equal(rows[0].lastGamePitches, null)
  assert.equal(rows[0].appearancesLast7, null)
  assert.equal(rows[0].pitchesLast7, null)
  assert.equal(rows[0].pattern, null)
  const html = render({ read: read({
    activeBullpen: { population_basis: 'basis', arm_count: 1, arms: [arm({ last_appearance: null, workload: {} })] },
  }) })
  assert.ok(text(html).includes('— rest'))
  assert.ok(text(html).includes('— app'))
  assert.equal(text(html).includes('Last P'), false)
})

test('multi-day pattern is used only for the supplied true back-to-back fact', () => {
  const rows = getActiveBullpenRows(read().activeBullpen)
  assert.equal(rows[0].pattern, 'B2B')
  assert.equal(rows[1].pattern, null)
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

test('pitcher handoff makes the whole row a native keyboard target using the existing callback', async () => {
  const html = render({ read: read(), onSelectPitcher: () => {} })
  assert.match(html, /<button[^>]*class="active-arm-row active-arm-row--with-last-p"[^>]*aria-label="Open pitcher context for Christopher Longname-Example"/)
  assert.equal((html.match(/<button/g) || []).length, 2)
  assert.equal(html.includes('View pitcher'), false)
  assert.equal(html.includes('Open pitcher</button>'), false)

  const source = await readFile(
    new URL('../src/components/bullpen/board/TeamBoardActiveBullpen.jsx', import.meta.url),
    'utf8',
  )
  const rowSource = await readFile(
    new URL('../src/components/bullpen/board/ActiveArmRow.jsx', import.meta.url),
    'utf8',
  )
  assert.ok(source.includes('onSelectPitcher(row.pitcherId, event.currentTarget)'))
  assert.equal(source.includes('onClick={() => onSelectPitcher'), false)
  assert.ok(rowSource.includes("event.key !== 'Enter' && event.key !== ' '"))
  assert.ok(rowSource.includes('event.preventDefault()'))
})

test('Last P is conditional and absent rather than a permanently withheld column', () => {
  const withoutLastP = read({
    activeBullpen: {
      population_basis: 'basis',
      arm_count: 1,
      arms: [arm({ last_appearance: { date: '2026-08-15', pitches: null } })],
    },
  })
  const html = render({ read: withoutLastP })

  assert.equal(text(html).includes('Last P'), false)
  assert.equal(html.includes('active-arm-row--with-last-p'), false)
})

test('pitcher selection uses normal history navigation to the standalone destination', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('navigate(buildPitcherHref(pitcherId'))
  assert.equal(source.includes('boardPitcherOriginRef'), false)
  assert.equal(source.includes('restoreBoardPitcherFocusRef'), false)
  assert.equal(source.includes('fixed inset-0'), false)
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

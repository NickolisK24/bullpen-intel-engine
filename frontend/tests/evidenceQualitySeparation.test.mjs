// Evidence quality is not operating state (availability engine v2 / Team State
// v3_phase_6). The backend decides operating status and evidence quality; the
// frontend must never turn a missing or stale status back into "On Watch", and it
// renders the backend's team-level evidence scope as a compact note, not a
// weaker Team State.
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

const { getPitcherSearchResultView } = await server.ssrLoadModule(
  '/src/components/bullpen/PitcherSearch.jsx',
)
const { getAvailabilityBadgeView } = await server.ssrLoadModule(
  '/src/components/bullpen/availabilityView.js',
)
const { PITCHER_READ_LABELS } = await server.ssrLoadModule('/src/utils/pitcherLabels.js')
const {
  default: TeamBoardAnswerBlock,
  getTeamBoardAnswerView,
  TEAM_STATE_EVIDENCE_SCOPE_REASON,
} = await server.ssrLoadModule('/src/components/bullpen/board/TeamBoardAnswerBlock.jsx')

const team = { team_id: 120, team_name: 'Washington Nationals', team_abbreviation: 'WSH' }
const NOTE = '3 of 11 active relievers have not pitched in the last 14 days; complete game records confirm their rest, without a current workload score.'

function read(teamStateSection) {
  return {
    team,
    representedDate: '2026-10-08',
    freshness: { data_through: '2026-10-08', is_current: true },
    teamState: {
      available: true,
      public_state: 'fresh',
      public_label: 'Fresh',
      summary: 'Strong rested coverage gives the active bullpen operating room.',
      unavailable_message: null,
      data_through: '2026-10-08',
    },
    summary: 'Strong rested coverage gives the active bullpen operating room.',
    activeBullpen: { arm_count: 11, arms: [] },
    sectionStatus: {
      team_state: teamStateSection,
      active_bullpen: { status: 'available', limitations: [] },
    },
  }
}

const text = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

test('Pitcher Search never invents On Watch for a missing status', () => {
  const view = getPitcherSearchResultView({ player_id: 1, player_name: 'Idle Arm' })
  assert.equal(view.availability, null)
  assert.equal(view.availabilityPayload.availability_status, null)
  const badge = getAvailabilityBadgeView(view.availabilityPayload)
  assert.notEqual(badge.label, 'On Watch')
  assert.notEqual(badge.status, 'Monitor')
})

test('Watch Arm means workload attention only, never unclear or old data', () => {
  const definition = PITCHER_READ_LABELS.WATCH_ARM.definition
  assert.doesNotMatch(definition, /not fully clear/i)
  assert.match(definition, /Old or missing workload data is never a Watch Arm/)
})

test('a published Team State shows the backend evidence scope as a compact, neutral note', () => {
  const answer = read({
    status: 'partial',
    reason_code: TEAM_STATE_EVIDENCE_SCOPE_REASON,
    limitations: [NOTE],
  })
  const view = getTeamBoardAnswerView(answer)
  assert.equal(view.limitation.reasonCode, 'team_state_evidence_scope_disclosed')
  const html = renderToStaticMarkup(React.createElement(TeamBoardAnswerBlock, { read: answer }))
  const rendered = text(html)
  assert.ok(rendered.includes('Workload evidence'))
  assert.ok(rendered.includes(NOTE))
  assert.ok(!rendered.includes('Limited read'))
  // The Team State itself is untouched.
  assert.match(html, /aria-label="Team State: Fresh"/)
})

test('without a disclosed scope nothing extra renders', () => {
  const html = renderToStaticMarkup(React.createElement(TeamBoardAnswerBlock, {
    read: read({ status: 'available', limitations: [] }),
  }))
  assert.ok(!text(html).includes('Workload evidence'))
})

test('Methodology no longer claims stale or missing evidence always withholds the read', async () => {
  const source = (await readFile('src/components/methodology/Methodology.jsx', 'utf8'))
    .replace(/\s+/g, ' ')
  assert.ok(!source.includes('When the evidence is missing or stale, it withholds the read instead of guessing.'))
  assert.ok(source.includes('never as On Watch'))
  assert.ok(source.includes('regular-season and postseason games'))
})

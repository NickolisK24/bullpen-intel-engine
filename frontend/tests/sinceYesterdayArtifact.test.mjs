import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { readFileSync } from 'node:fs'

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
const { loadSinceYesterdayCitation } = await server.ssrLoadModule('/src/utils/sinceYesterdayArtifact.js')
const { ArtifactView } = await server.ssrLoadModule('/src/components/share/PublicShareArtifactPage.jsx')

test.after(async () => server.close())

const item = {
  teamId: 147,
  teamAbbr: 'NYY',
  previousDate: '2026-08-23',
  currentDate: '2026-08-24',
}

const artifact = {
  public_id: 'change123',
  artifact_type: 'since_yesterday_change',
  product_date: '2026-08-24',
  published_at: '2026-08-25T12:00:00',
  team: { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
  change: {
    primary_delta: { label: 'Rested options', previous: 4, current: 0, net_delta: -4 },
  },
  copy: {
    headline: 'New York has less bullpen room than yesterday.',
    summary: 'New York has fewer rested options than yesterday.',
    why: 'That leaves fewer ways through a close game.',
    description: 'New York has fewer rested options than yesterday.',
  },
  evidence: [{ label: 'Rested options', yesterday: 4, today: 0 }],
  freshness: { previous_data_through: '2026-08-23', current_data_through: '2026-08-24' },
  routes: { share_url: '/share/change123', team_url: '/bullpen?view=board&team=NYY&source=share' },
}

test('lazy citation resolution uses one bounded owner request and canonical URL', async () => {
  const calls = []
  const model = await loadSinceYesterdayCitation(item, {
    fetchArtifact: async (...args) => {
      calls.push(args)
      return { available: true, artifact }
    },
  })
  assert.deepEqual(calls, [[147, { current_date: '2026-08-24', prior_date: '2026-08-23' }]])
  assert.equal(model.destinationUrl, 'https://baseballos.app/share/change123')
  assert.equal(model.shareText, artifact.copy.description)
})

test('malformed or unavailable citations fail closed', async () => {
  assert.equal(await loadSinceYesterdayCitation(item, {
    fetchArtifact: async () => ({ available: false }),
  }), null)
  assert.equal(await loadSinceYesterdayCitation(item, {
    fetchArtifact: async () => ({ available: true, artifact: { ...artifact, artifact_type: 'team_state' } }),
  }), null)
})

test('public artifact page renders the frozen change, evidence, dates, and current handoff', () => {
  const html = renderToStaticMarkup(React.createElement(ArtifactView, { artifact, superseded: false }))
  assert.match(html, /Published change/)
  assert.match(html, /New York has less bullpen room than yesterday/)
  assert.match(html, /Rested options/)
  assert.match(html, />4</)
  assert.match(html, />0</)
  assert.match(html, /August 23/)
  assert.match(html, /August 24/)
  assert.match(html, /Open current New York Yankees bullpen board/)
  assert.doesNotMatch(html, /current_snapshot_id|prior_snapshot_id|prediction|recommendation/)
})

test('change page remains mobile-safe and uses no horizontal-scroll contract', () => {
  const source = readFileSync('src/components/share/PublicShareArtifactPage.jsx', 'utf8')
  assert.doesNotMatch(source, /overflow-x-auto|min-w-\[/)
  assert.match(source, /grid-cols-1/)
})

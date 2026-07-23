import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})
after(async () => server.close())

const mod = await server.ssrLoadModule('/src/utils/shareCardArtifact.js')
const renderer = await server.ssrLoadModule('/src/utils/evidenceCardRenderer.js')

function projection(cardOverrides = {}) {
  return {
    available: true,
    card: {
      source: 'immutable_share_artifact',
      public_id: 'abc123def456',
      artifact_type: 'team_state',
      render_version: 'team-state-1.0.0',
      payload_version: 'team-state-1.0.0',
      team: { team_id: 147, team_name: 'Test Club', team_abbreviation: 'TST' },
      headline: 'Operationally Constrained',
      status_code: 'operationally_constrained',
      summary: 'Two late-inning arms are down.',
      receipts: [{ category: 'workload', detail: 'Heavy recent relief workload.' }],
      product_date: '2026-07-20',
      trust: { confidence: 'high', freshness_state: 'current' },
      ...cardOverrides,
    },
  }
}

test('adapter projects the immutable artifact into the team card shape', () => {
  const card = mod.buildTeamShareCardFromArtifact(projection())
  assert.equal(card.cardType, 'team')
  assert.equal(card.teamName, 'Test Club')
  assert.equal(card.teamAbbreviation, 'TST')
  assert.equal(card.stateLabel, 'Operationally Constrained')
  assert.deepEqual(card.receipts, ['Heavy recent relief workload.'])
  assert.equal(card.dataThrough, '2026-07-20')
  assert.equal(card.dataThroughLabel, 'July 20, 2026')
  assert.match(card.destinationUrl, /baseballos\.app\/bullpen\?view=board&team=TST/)
  assert.equal(card.fileName, 'baseballos-tst-bullpen-2026-07-20.png')
  assert.match(card.headline, /TWO LATE-INNING ARMS ARE DOWN/)
  assert.equal(card.source, 'immutable_share_artifact')
  assert.equal(card.artifactPublicId, 'abc123def456')
})

test('adapter omits legacy tracker card_version/story_angle so tracking still works', () => {
  const card = mod.buildTeamShareCardFromArtifact(projection())
  assert.equal(card.cardVersion, undefined)
  assert.equal(card.storyAngle, undefined)
})

test('adapter returns null when no published artifact backs the card', () => {
  assert.equal(mod.buildTeamShareCardFromArtifact({ available: false, reason: 'no_published_artifact' }), null)
  assert.equal(mod.buildTeamShareCardFromArtifact(null), null)
  assert.equal(mod.buildTeamShareCardFromArtifact(undefined), null)
  assert.equal(mod.buildTeamShareCardFromArtifact({ available: true }), null)
})

test('adapter refuses a non-artifact source (never fabricates a card)', () => {
  const spoofed = projection()
  spoofed.card.source = 'legacy_client_composition'
  assert.equal(mod.buildTeamShareCardFromArtifact(spoofed), null)
})

test('the existing renderer renders the adapted card without error', () => {
  const card = mod.buildTeamShareCardFromArtifact(projection())
  const svg = renderer.renderEvidenceCardSvg(card)
  assert.equal(typeof svg, 'string')
  assert.ok(svg.includes('TEST CLUB'))
})

test('EVIDENCE_CARD_ORIGIN is exported so entry points do not depend on the legacy composer', () => {
  assert.equal(mod.EVIDENCE_CARD_ORIGIN, 'https://baseballos.app')
})

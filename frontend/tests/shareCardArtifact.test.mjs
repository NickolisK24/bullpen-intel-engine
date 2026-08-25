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

function projection(stateOverrides = {}) {
  return {
    available: true,
    artifact: {
      public_id: 'abc123def456',
      artifact_type: 'team_state',
      lifecycle_state: 'published',
      product_date: '2026-07-20',
      copy: {
        description: 'Two late-inning arms are down.',
        alt_text: 'Published Team State for Test Club: Stretched.',
      },
      evidence: [{ category: 'workload', detail: 'Heavy recent relief workload.' }],
      routes: { share_url: '/share/abc123def456' },
      card: {
        card_version: 'team-state-1.2.0',
        artifact_context: { data_through: '2026-07-20' },
        team: { team_id: 147, canonical_name: 'Test Club', abbreviation: 'TST' },
        state: {
          public_state: 'stretched',
          public_label: 'Stretched',
          headline: 'Test Club bullpen — Stretched',
          why: 'Two late-inning arms are down.',
          ...stateOverrides,
        },
        limitations: ['Describes observed workload; does not predict usage.'],
      },
    },
  }
}

test('adapter projects the immutable artifact into the team card shape', () => {
  const card = mod.buildTeamShareCardFromArtifact(projection())
  assert.equal(card.cardType, 'team')
  assert.equal(card.teamName, 'Test Club')
  assert.equal(card.teamAbbreviation, 'TST')
  assert.equal(card.stateLabel, 'Stretched')
  assert.deepEqual(card.receipts, ['Heavy recent relief workload.'])
  assert.equal(card.dataThrough, '2026-07-20')
  assert.equal(card.dataThroughLabel, 'July 20, 2026')
  assert.equal(card.destinationUrl, 'https://baseballos.app/share/abc123def456')
  assert.equal(card.fileName, 'baseballos-tst-team-state-2026-07-20.png')
  assert.match(card.headline, /TEST CLUB BULLPEN — STRETCHED/)
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
  const wrongVersion = projection()
  wrongVersion.artifact.card.card_version = 'team-state-1.1.0'
  assert.equal(mod.buildTeamShareCardFromArtifact(wrongVersion), null)
})

test('adapter refuses a non-published artifact (never fabricates a card)', () => {
  const spoofed = projection()
  spoofed.artifact.lifecycle_state = 'withdrawn'
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

// ── H-11: internal readiness wording never reaches a shareable card ─────────

test('the state badge carries a canonical public Team State, not internal wording', () => {
  const card = mod.buildTeamShareCardFromArtifact(projection())
  const svg = renderer.renderEvidenceCardSvg(card)

  assert.ok(svg.includes('BASEBALLOS STATE · STRETCHED'))
  for (const internal of [
    'Operationally Stable', 'Operationally Constrained', 'Operationally Stressed',
    'OPERATIONALLY STABLE', 'OPERATIONALLY CONSTRAINED', 'OPERATIONALLY STRESSED',
    'operationally_stable', 'operationally_constrained', 'operationally_stressed',
  ]) {
    assert.equal(svg.includes(internal), false, `card must not render ${internal}`)
    assert.equal(String(card.altText).includes(internal), false, `alt text must not carry ${internal}`)
  }
})

test('a non-canonical state label withholds the card instead of stamping it', () => {
  // Contract violation only: the backend projection resolves the public label
  // from the artifact's status code, so this can never arrive in normal
  // operation. If it ever did, no card is better than an internal word on a
  // shareable image.
  for (const leaked of ['Operationally Stressed', 'operationally_stressed', 'Stable', 'Unknown', '']) {
    const spoofed = projection({ public_label: leaked })
    assert.equal(mod.buildTeamShareCardFromArtifact(spoofed), null, leaked)
  }
})

test('every canonical public Team State renders a badge', () => {
  for (const label of ['Fresh', 'Stretched', 'Vulnerable']) {
    const card = mod.buildTeamShareCardFromArtifact(projection({ public_label: label }))
    assert.ok(card, label)
    assert.ok(renderer.renderEvidenceCardSvg(card).includes(`BASEBALLOS STATE · ${label.toUpperCase()}`))
  }
})

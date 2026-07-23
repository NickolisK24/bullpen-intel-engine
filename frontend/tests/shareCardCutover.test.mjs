import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

// Share Cards SC-03A — legacy cutover foundation proofs.
//
// These are source-string proofs: the goal is not to re-test the adapter's
// behavior (shareCardArtifact.test.mjs covers that) but to prove that the three
// ACTIVE Share Card entry points now consume the canonical, artifact-backed
// projection and no longer compose card intelligence in the browser. There must
// be exactly one source of truth for the Share Card: the immutable Share
// Artifact served by the backend.

const read = relPath => readFileSync(new URL(relPath, import.meta.url), 'utf8')

const board = read('../src/components/bullpen/board/TonightsBullpenBoard.jsx')
const comparisonView = read('../src/components/bullpen/board/BullpenComparisonView.jsx')
const stories = read('../src/components/stories/Stories.jsx')
const adapter = read('../src/utils/shareCardArtifact.js')
const api = read('../src/utils/api.js')

const ENTRY_POINTS = [
  ['TonightsBullpenBoard.jsx', board],
  ['BullpenComparisonView.jsx', comparisonView],
  ['Stories.jsx', stories],
]

const LEGACY_COMPOSERS = [
  'buildTeamEvidenceCard',
  'buildComparisonEvidenceCard',
  'selectTeamStory',
  'selectComparisonStory',
]

test('no active entry point imports the deprecated legacy composer modules', () => {
  for (const [name, source] of ENTRY_POINTS) {
    assert.equal(
      source.includes("from '../../../utils/evidenceCardModel'")
        || source.includes("from '../../utils/evidenceCardModel'"),
      false,
      `${name} must not import evidenceCardModel`,
    )
    assert.equal(
      source.includes("from '../../../utils/evidenceCardStory'")
        || source.includes("from '../../utils/evidenceCardStory'"),
      false,
      `${name} must not import evidenceCardStory`,
    )
  }
})

test('no active entry point calls any legacy client-side card composer', () => {
  for (const [name, source] of ENTRY_POINTS) {
    for (const composer of LEGACY_COMPOSERS) {
      assert.equal(source.includes(composer), false, `${name} must not reference ${composer}`)
    }
  }
})

test('the board sources its card from the canonical immutable artifact', () => {
  // Fetches the governed projection...
  assert.ok(board.includes('getTeamShareCard'))
  assert.ok(board.includes("from '../../../utils/api'"))
  // ...and adapts ONLY that projection into the renderer/share-menu shape.
  assert.ok(board.includes('buildTeamShareCardFromArtifact(shareCard.data)'))
  assert.ok(board.includes("from '../../../utils/shareCardArtifact'"))
})

test('the board never falls back to legacy composition when the artifact is absent', () => {
  // teamCard is assigned purely from the artifact adapter, with no `||`
  // fallback to a client-composed card. When the adapter returns null the share
  // menu shows its controlled unavailable state.
  const teamCardLine = board
    .split('\n')
    .find(line => line.includes('const teamCard ='))
  assert.ok(teamCardLine, 'expected a `const teamCard =` assignment in the board')
  assert.equal(teamCardLine.trim(), 'const teamCard = buildTeamShareCardFromArtifact(shareCard.data)')
  for (const composer of LEGACY_COMPOSERS) {
    assert.equal(teamCardLine.includes(composer), false)
  }
})

test('the comparison view yields a controlled-unavailable card, never a composed one', () => {
  // No comparison Team State artifact exists in the immutable architecture yet,
  // so the comparison card is explicitly unavailable (null) rather than composed
  // client-side. The share menu handles the null with its unavailable state.
  assert.ok(comparisonView.includes('const cardModel = null'))
  assert.equal(comparisonView.includes('buildComparisonEvidenceCard'), false)
})

test('the stories surface links only, sourcing its origin from the artifact module', () => {
  // Stories is link-only (no share card), but its origin constant must come from
  // the artifact module, not the deprecated composer, so nothing on this surface
  // depends on the legacy card intelligence.
  assert.ok(stories.includes("import { EVIDENCE_CARD_ORIGIN } from '../../utils/shareCardArtifact'"))
  assert.ok(stories.includes('${EVIDENCE_CARD_ORIGIN}${story.href}'))
})

test('the adapter refuses anything but a verified immutable-artifact projection', () => {
  // The single source of truth is enforced in the adapter: it composes no
  // intelligence and only accepts the backend compatibility projection.
  assert.ok(adapter.includes("immutable_share_artifact"))
  assert.ok(adapter.includes('available'))
  // It never imports the legacy composer modules.
  assert.equal(adapter.includes('evidenceCardModel'), false)
  assert.equal(adapter.includes('evidenceCardStory'), false)
})

test('the api client reads the governed backend share-card endpoint', () => {
  assert.ok(api.includes('getTeamShareCard'))
  assert.ok(api.includes('/share-cards/team-state/'))
})

test('the legacy composer modules are marked deprecated / REMOVE_LATER', () => {
  const model = read('../src/utils/evidenceCardModel.js')
  const story = read('../src/utils/evidenceCardStory.js')
  assert.match(model, /DEPRECATED — REMOVE_LATER/)
  assert.match(story, /DEPRECATED — REMOVE_LATER/)
})

import assert from 'node:assert/strict'
import test, { after } from 'node:test'
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
  STORY_TONES,
  storyTone,
  getMastheadView,
} = await server.ssrLoadModule('/src/components/stories/storiesPresentationView.js')

// ── Tones ───────────────────────────────────────────────────────────────────

test('story tones cover the four neutral display situations', () => {
  assert.deepEqual(Object.keys(STORY_TONES).sort(), ['neutral', 'rest', 'stress', 'watch'])
  for (const key of ['stress', 'watch', 'rest', 'neutral']) {
    assert.ok(STORY_TONES[key].color)
    assert.ok(STORY_TONES[key].dot)
  }
})

test('storyTone resolves a known key and falls back to neutral', () => {
  assert.equal(storyTone('stress'), STORY_TONES.stress)
  assert.equal(storyTone('rest'), STORY_TONES.rest)
  assert.equal(storyTone('unknown'), STORY_TONES.neutral)
  assert.equal(storyTone(undefined), STORY_TONES.neutral)
})

// ── Masthead ────────────────────────────────────────────────────────────────

test('the masthead reports the data window in plain language', () => {
  const dashboard = {
    freshness: { data_through: '2026-06-05', is_current: true, sync_status: 'success' },
  }
  const masthead = getMastheadView(dashboard, new Date('2026-06-06T12:00:00Z'))
  assert.ok(/Updated after completed games through Jun 5, 2026/.test(masthead.dataLine))
  assert.ok(masthead.editionDate.includes('2026'))
  assert.equal(masthead.isLive, true)
  const cold = getMastheadView({}, new Date('2026-06-06T12:00:00Z'))
  assert.equal(cold.dataLine, 'Waiting on the first completed games')
})

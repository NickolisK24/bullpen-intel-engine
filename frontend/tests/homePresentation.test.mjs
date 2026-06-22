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
  HOME_TONES,
  homeTone,
  buildHomeTeamHref,
  getMastheadView,
} = await server.ssrLoadModule('/src/components/home/homePresentationView.js')

// ── Tones ───────────────────────────────────────────────────────────────────

test('home tones cover the four neutral display situations', () => {
  assert.deepEqual(Object.keys(HOME_TONES).sort(), ['neutral', 'rest', 'stress', 'watch'])
  for (const key of ['stress', 'watch', 'rest', 'neutral']) {
    assert.ok(HOME_TONES[key].color)
    assert.ok(HOME_TONES[key].dot)
  }
})

test('homeTone resolves a known key and falls back to neutral', () => {
  assert.equal(homeTone('stress'), HOME_TONES.stress)
  assert.equal(homeTone('rest'), HOME_TONES.rest)
  assert.equal(homeTone('unknown'), HOME_TONES.neutral)
  assert.equal(homeTone(undefined), HOME_TONES.neutral)
})

// ── Team deep links ─────────────────────────────────────────────────────────

test('buildHomeTeamHref deep-links into the bullpen board with a source tag', () => {
  assert.equal(
    buildHomeTeamHref({ team_abbreviation: 'MIL' }, 'home-hero'),
    '/bullpen?view=board&team=MIL&source=home-hero',
  )
  assert.equal(
    buildHomeTeamHref({ team_id: 158 }),
    '/bullpen?view=board&team=158&source=home',
  )
  assert.equal(buildHomeTeamHref({}), null)
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

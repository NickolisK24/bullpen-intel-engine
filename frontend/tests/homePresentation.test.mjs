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
  getHomeRosterStatusLine,
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

// ── Home roster line (CRC-10: reads Roster Authority, not legacy roster_status) ──

test('the home roster line reads the invariant off-roster count from Roster Authority', () => {
  const board = { roster_authority: { counts: { inactive_roster_context_count: 3 } } }
  assert.equal(getHomeRosterStatusLine(board), '3 off the active roster')
  const one = { roster_authority: { counts: { inactive_roster_context_count: 1 } } }
  assert.equal(getHomeRosterStatusLine(one), '1 off the active roster')
})

test('the home roster line reads None when no arms are off the active roster or no board', () => {
  assert.equal(
    getHomeRosterStatusLine({ roster_authority: { counts: { inactive_roster_context_count: 0 } } }),
    'None off the active roster',
  )
  assert.equal(getHomeRosterStatusLine(null), 'None off the active roster')
  assert.equal(getHomeRosterStatusLine({}), 'None off the active roster')
})

test('the home roster line ignores the retired legacy roster_status summary', () => {
  // A board carrying a (bogus) legacy roster_status must not affect the line — only Roster
  // Authority drives the count. This is the CRC-10 correctness fix: the old line read the
  // default board's legacy roster_status.inactive_context_count, which was always 0.
  const board = {
    roster_status: { inactive_context_count: 0, active_mlb_count: 999 },
    roster_authority: { counts: { inactive_roster_context_count: 5 } },
  }
  assert.equal(getHomeRosterStatusLine(board), '5 off the active roster')
})

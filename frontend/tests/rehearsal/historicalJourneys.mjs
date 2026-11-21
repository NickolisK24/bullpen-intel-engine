// Called by the disposable PostgreSQL rollback test with its local Flask adapter.
import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { chromium, expect } from '@playwright/test'
import { build, preview } from 'vite'

const port = Number(process.argv[2])
assert(Number.isInteger(port) && port > 0 && port <= 65535)
const dir = await mkdtemp(join(tmpdir(), 'baseballos-product-rehearsal-'))
let server, browser
try {
  // Build only the client under test. The production build also generates public export files.
  const vite = { configFile: false, envDir: false, publicDir: false, logLevel: 'error',
    esbuild: { jsx: 'automatic' }, build: { outDir: dir, emptyOutDir: true } }
  await build(vite)
  server = await preview({ ...vite, preview: { host: '127.0.0.1', port: 0,
    proxy: { '/api/sync-v3/': `http://127.0.0.1:${port}` } } })
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`
  browser = await chromium.launch({ executablePath: process.env.SYNC_V3_TEST_CHROMIUM || undefined })
  const context = await browser.newContext({ serviceWorkers: 'block' })
  const unexpected = [], reads = [], errors = []
  await context.route('**/*', route => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== origin || request.method() !== 'GET' || (url.pathname.startsWith('/api/')
        && !url.pathname.startsWith('/api/sync-v3/'))) {
      if (url.pathname.startsWith('/api/') || request.method() !== 'GET') unexpected.push(request.method() + ' ' + url.pathname)
      return route.abort()
    }
    if (url.pathname.startsWith('/api/')) reads.push(url.pathname)
    return route.continue()
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  const visit = path => page.goto(origin + path)
  const heading = name => page.getByRole('heading', { name, exact: true })
  const link = name => page.getByRole('link', { name, exact: true })
  if (process.argv[3] === 'selected-slate') {
    const revision = Number(process.argv[4] ?? 1)
    assert(Number.isSafeInteger(revision) && revision > 0)
    const prefix = '/api/sync-v3/revisions/' + revision
    await visit('/dashboard?rehearsalRevision=' + revision)
    await expect(page.getByRole('link', { name: /Open the Team Board for/ })).toHaveCount(30)
    await link('Open the Team Board for Boston Red Sox').click()
    await expect(heading('Boston Red Sox')).toBeVisible()
    const generation = new URL(page.url()).searchParams.get('rehearsalGeneration')
    assert.match(generation, /^[a-f0-9]{64}$/)
    await link('Inspect evidence for this edition').click()
    await expect(heading('Historical evidence · Revision ' + revision)).toBeVisible({ timeout: 30_000 })

    await visit(`/tonight?rehearsalRevision=${revision}&rehearsalGeneration=${generation}`)
    const card = page.getByTestId('tonight-game-card').first()
    await expect(card).toBeVisible()
    const game = await card.getAttribute('data-game-pk')
    assert.match(game, /^[1-9][0-9]*$/)
    await card.locator('[data-link="matchup"]').first().click()
    await expect(heading('Historical Bullpen Comparison')).toBeVisible()
    assert.equal(new URL(page.url()).searchParams.get('rehearsalGeneration'), generation)
    assert.deepEqual(reads, ['league', 'teams/111/board', 'trust', 'tonight', 'matchups/' + game]
      .map(suffix => prefix + '/' + suffix))
  } else if (process.argv[3] === 'off-day') {
    await visit('/tonight?rehearsalRevision=1')
    await expect(page.getByText('No games on the represented slate.')).toBeVisible()
    await expect(page.getByTestId('tonight-game-card')).toHaveCount(0)
    await link('Open this League edition').click()
    await expect(page.getByRole('link', { name: /Open the Team Board for/ })).toHaveCount(30)
    assert.deepEqual(reads, ['/api/sync-v3/revisions/1/tonight', '/api/sync-v3/revisions/1/league'])
  } else {
    assert.equal(process.argv[3], 'rollback')
    const prefix = '/api/sync-v3/revisions/3'

    await visit('/dashboard?rehearsalRevision=3')
    await expect(page.getByRole('link', { name: /Open the Team Board for/ })).toHaveCount(30)
    await link('Open the Team Board for Boston Red Sox').click()
    await expect(heading('Boston Red Sox')).toBeVisible()
    const generation = new URL(page.url()).searchParams.get('rehearsalGeneration')
    assert.match(generation, /^[a-f0-9]{64}$/)
    const board = new URL(page.url()).pathname + new URL(page.url()).search
    await link('Rehearsal Arm 11101').click()
    await expect(heading('Rehearsal Arm 11101')).toBeVisible()
    await expect(page.locator('dt').filter({ hasText: 'Appearances / 7d' }).locator('..').locator('dd')).toHaveText('1')
    await expect(page.locator('dt').filter({ hasText: 'Days since bullpen outing' }).locator('..').locator('dd'))
      .toHaveText('1 as of 2026-07-30')
    await link('Open Boston Red Sox Team Board').click()
    await expect(heading('Boston Red Sox')).toBeVisible()
    assert.equal(page.url(), origin + board)
    await link('Inspect editorial observations').click()
    await expect(heading('Historical story evidence · Boston Red Sox')).toBeVisible()
    await expect(page.getByRole('heading', { name: /concentration pressure/i })).toBeVisible()
    await link('Open this Team Board edition').click()
    assert.equal(page.url(), origin + board)
    await link('Inspect evidence for this edition').click()
    await expect(heading('Historical evidence · Revision 3')).toBeVisible()
    await expect(page.getByText('candidate_roster_depth_v1', { exact: true })).toBeVisible()

    await visit('/tonight?rehearsalRevision=3')
    await page.locator('[data-game-pk="10101"] [data-link="matchup"]').first().click()
    await expect(heading('Historical Bullpen Comparison')).toBeVisible()
    assert.equal(new URL(page.url()).searchParams.get('rehearsalGeneration'), generation)

    await visit('/search?rehearsalRevision=3')
    await page.getByRole('searchbox').fill('Former Boston')
    await link('Open Former Boston Reliever').click()
    await expect(heading('Former Boston Reliever')).toBeVisible()
    assert.equal(new URL(page.url()).searchParams.get('rehearsalGeneration'), generation)
    await page.getByText('Pitcher identity sources', { exact: true }).click()
    await expect(page.getByText('BaseballOS pitcher identity export', { exact: false })).toBeVisible()
    await expect(page.getByText('Removed from the active roster', { exact: false })).toHaveCount(1)
    await visit('/pitcher/8999?rehearsalRevision=2')
    await expect(heading('Former Boston Reliever')).toBeVisible()
    await expect(page.getByText('Removed from the active roster', { exact: false })).toHaveCount(0)

    await visit('/history/team/BOS?rehearsalRevision=3')
    await expect(heading('Boston Red Sox historical rehearsal')).toBeVisible()
    const rollback = page.getByRole('article').filter({ has: heading('Revision 3 · Rollback') }).first()
    const departure = rollback.locator('details').filter({ has: page.locator('summary').filter({ hasText: 'Former Boston Reliever' }) })
    await departure.locator('summary').click()
    await departure.getByRole('link', { name: 'Pitcher Detail for this revision' }).click()
    await expect(heading('Former Boston Reliever')).toBeVisible()
    assert.equal(new URL(page.url()).searchParams.get('rehearsalGeneration'), generation)

    const wrong = generation.startsWith('f') ? '0'.repeat(64) : 'f'.repeat(64)
    await visit(board.replace(generation, wrong))
    await expect(page.getByText('The requested historical Team Board edition could not be verified.')).toBeVisible()
    await expect(heading('Boston Red Sox')).toHaveCount(0)
    assert.deepEqual(reads, [
      prefix + '/league', prefix + '/teams/111/board', prefix + '/pitchers/9111', prefix + '/teams/111/board', prefix + '/teams/111/stories',
      prefix + '/teams/111/board', prefix + '/trust', prefix + '/tonight', prefix + '/matchups/10101',
      prefix + '/search', prefix + '/pitchers/8999', '/api/sync-v3/revisions/2/pitchers/8999',
      '/api/sync-v3/history/teams/BOS/revisions/3', prefix + '/pitchers/8999', prefix + '/teams/111/board',
    ])
  }
  assert.deepEqual(unexpected, [])
  assert.deepEqual(errors, [])
  console.log(`Historical product journeys verified with ${reads.length} local GET requests.`)
} finally {
  try {
    await browser?.close()
  } finally {
    if (server) await new Promise(resolve => server.httpServer.close(resolve))
    await rm(dir, { recursive: true, force: true })
  }
}

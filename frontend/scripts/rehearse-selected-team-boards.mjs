// Run against a local production build and archived Flask core/details pairs.
import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import { chromium, expect } from '@playwright/test'

const [directory, origin] = process.argv.slice(2)
if (!directory || !origin || !/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) {
  throw new Error('Expected a directory of TEAM.json pairs and a loopback preview URL')
}
const pairs = []
for (const file of await readdir(directory)) {
  if (!/^\d+\.json$/.test(file)) continue
  const pair = JSON.parse(await readFile(path.join(directory, file), 'utf8'))
  assert.equal(file, pair[0].team.team_id + '.json')
  assert.deepEqual(pair[0].publication_identity, pair[1].publication_identity)
  pairs.push(pair)
}
assert.equal(pairs.length, 30)
const teams = pairs.map(([core]) => core.team)
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })
try {
  for (const [core, details] of pairs) {
    const page = await browser.newPage({ serviceWorkers: 'block' })
    const board = '/api/bullpen/teams/' + core.team.team_id + '/board-v2/'
    let receivedBoundRequest = false
    await page.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/bullpen/teams') return route.fulfill({ json: teams })
      if (url.pathname === board + 'core') return route.fulfill({ json: core })
      if (url.pathname === board + 'details') {
        receivedBoundRequest = Object.entries(core.publication_identity)
          .every(([key, value]) => url.searchParams.get(key) === String(value))
        return route.fulfill({ json: details })
      }
      if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 404, json: {} })
      return url.origin === origin ? route.continue() : route.abort()
    })
    await page.goto(origin + '/bullpen?team=' + core.team.team_abbreviation)
    const active = page.getByTestId('team-board-active-bullpen')
    await expect(active).toContainText(core.active_bullpen.arms[0].name)
    await expect(page.getByTestId('team-board-answer-block')).toContainText(core.team_state.public_label)
    await expect(page.getByTestId('team-board-recent-usage')).toBeVisible()
    await expect.poll(() => receivedBoundRequest).toBe(true)
    console.log(core.team.team_abbreviation, core.team_state.public_label)
    await page.close()
  }
} finally {
  await browser.close()
}

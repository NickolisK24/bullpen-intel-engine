import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {
  dailyEditionPayload,
  discoveryPayload,
  finderPayload,
  historyPayload,
  matchupPayload,
  pitcherPayload,
  shareArtifact,
  teamBoardCore,
  teamBoardDetails,
  teamShareProjection,
  teams,
} from './fixtures.mjs'

const leagueTeams = {
  capability: 'league_team_state_listing_v1', version: '1.0.0', status: 'ok',
  expected_team_count: 2, team_count: 2, represented_team_count: 2, withheld_team_count: 0,
  ranking_applied: false, selection_made: false, prediction_applied: false,
  freshness: { data_through: '2026-09-02', freshness_state: 'current', is_current: true },
  teams: teams.map((team, index) => ({
    ...team,
    team_state: { available: true, public_state: index ? 'stretched' : 'fresh', public_label: index ? 'Stretched' : 'Fresh', data_through: '2026-09-02' },
  })),
}

async function installApiFixtures(page, {
  detailsFailure = false,
  deferDetails = false,
  corruptTeams = false,
  finderNoResults = false,
} = {}) {
  let releaseDetails
  const detailsGate = deferDetails
    ? new Promise(resolve => { releaseDetails = resolve })
    : null
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const json = body => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

    if (path === '/api/bullpen/teams') return json(corruptTeams ? { invalid: true } : teams)
    if (path === '/api/search') return json(discoveryPayload)
    if (path === '/api/bullpen/reliever-finder') {
      return json(finderNoResults ? {
        data: [],
        meta: { page: 1, total_pages: 0, total_results: 0, limit: 20, total_game_logs: 1, total_scored_pitchers: 1 },
      } : finderPayload)
    }
    if (path === '/api/bullpen/fatigue/101') return json(pitcherPayload)
    if (path === '/api/bullpen/pitchers/101/recent-work') return json({ status: 'available', appearances: [] })
    if (path === '/api/bullpen/teams/111/board-v2/core') return json(teamBoardCore)
    if (path === '/api/bullpen/teams/111/board-v2/details') {
      if (detailsGate) await detailsGate
      return detailsFailure
        ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'fixture detail outage' }) })
        : json(teamBoardDetails)
    }
    if (path === '/api/share-cards/team-state/111') return json(teamShareProjection)
    if (path === '/api/bullpen/matchups/999') return json(matchupPayload)
    if (path === '/api/bullpen/teams/BOS/history') return json(historyPayload)
    if (path === '/api/share-artifacts/fixture-share') return json({ status: 'published', artifact: shareArtifact })
    if (path.startsWith('/api/share-artifacts/')) return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    if (path === '/api/bullpen/league') return json({ team_states: leagueTeams, landscape: { items: [] } })
    if (path === '/api/bullpen/home') return json({ status: 'unavailable', reference_date: '2026-09-03', team_states: leagueTeams })
    if (path === '/api/bullpen/intelligence/today') return json(dailyEditionPayload)
    if (path === '/api/bullpen/stories') return json({ status: 'ok', stories: { items: [] } })
    if (path === '/api/bullpen/trust') return json({ status: 'ok' })
    return json({})
  })
  return { releaseDetails: releaseDetails || (() => {}) }
}

async function expectNoPageOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
}

test('skip link is first, becomes visible, and focuses main content', async ({ page }) => {
  await installApiFixtures(page)
  await page.goto('/search')
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Skip to main content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
})

test('Home supports direct entry without loading the legacy Dashboard carrier', async ({ page }) => {
  const requests = []
  page.on('request', request => requests.push(request.url()))
  await installApiFixtures(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  expect(requests.some(url => url.includes('/api/bullpen/dashboard'))).toBe(false)
})

test('cold Home renders the precomputed Daily Edition without refresh', async ({ page }) => {
  let todayRequests = 0
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/bullpen/intelligence/today') {
      todayRequests += 1
    }
  })
  await installApiFixtures(page)
  await page.goto('/')

  await expect(page.getByText('Lead disappeared late')).toBeVisible()
  await expect(page.getByText('The Daily Edition lead is temporarily unavailable.')).toHaveCount(0)
  expect(todayRequests).toBe(1)
})

test('route navigation focuses and announces the destination heading', async ({ page }) => {
  await installApiFixtures(page)
  await page.goto('/')
  await page.getByRole('link', { name: 'League Board', exact: true }).click()
  const heading = page.getByRole('heading', { level: 1, name: 'MLB Bullpen Picture' })
  await expect(heading).toBeVisible()
  await expect(page.locator('#main-content')).toBeFocused()
  await expect(page.locator('.sr-only[aria-live="polite"]')).toContainText('MLB Bullpen Picture')
  await expect(page).toHaveTitle(/MLB Bullpen League Board/)
  await page.getByRole('link', { name: 'Team Bullpens', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Team Board' })).toBeVisible()
  await expect(page.locator('#main-content')).toBeFocused()
})

test('Search is fully keyboard navigable into a pitcher destination', async ({ page }) => {
  await installApiFixtures(page)
  await page.goto('/')
  const searchDestination = page.getByRole('link', { name: 'Search', exact: true })
  await searchDestination.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL('/search')
  const search = page.getByRole('searchbox', { name: /Team, reliever, or matchup/i })
  await search.focus()
  await page.keyboard.type('Fixture')
  const result = page.getByRole('link', { name: 'Open Fixture Reliever' })
  await expect(result).toBeVisible()
  await result.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/pitcher\/101/)
  await expect(page.getByRole('heading', { level: 1, name: 'Fixture Reliever' })).toBeVisible()
  await expect(page.locator('#main-content')).toBeFocused()
})

test('Finder keyboard search, semantic sort, pagination, and native result link work', async ({ page }) => {
  const requests = []
  page.on('request', request => requests.push(request.url()))
  await installApiFixtures(page)
  await page.goto('/bullpen?view=pitchers')
  expect(requests.some(url => url.includes('/api/bullpen/reliever-finder'))).toBe(false)
  const search = page.getByRole('searchbox', { name: 'Search relievers by name' })
  await search.fill('Fixture')
  const sort = page.getByRole('button', { name: 'Pitches (7d)' })
  await sort.focus()
  await page.keyboard.press('Enter')
  await expect(sort.locator('xpath=ancestor::th')).toHaveAttribute('aria-sort', 'descending')
  const nextPage = page.getByRole('button', { name: 'Next page' })
  await nextPage.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => requests.some(url => url.includes('page=2'))).toBe(true)
  expect(requests.some(url => url.includes('limit=750'))).toBe(false)
  const result = page.getByRole('link', { name: 'Open pitcher detail for Fixture Reliever' })
  await result.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/pitcher\/101/)
})

test('Finder announces a deterministic no-results state', async ({ page }) => {
  await installApiFixtures(page, { finderNoResults: true })
  await page.goto('/bullpen?view=pitchers')
  await page.getByRole('searchbox', { name: 'Search relievers by name' }).fill('Fixture')
  await expect(page.getByRole('status')).toContainText(/no pitchers match/i)
})

test('Team Board renders its core answer before deferred details', async ({ page }) => {
  const fixtures = await installApiFixtures(page, { deferDetails: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByRole('heading', { level: 1, name: 'Team Board' })).toBeVisible()
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  await expect(page.getByText('Boston has several rested bullpen options.').first()).toBeVisible()
  await expect(page.getByText(/loading recent usage/i).first()).toBeVisible()
  fixtures.releaseDetails()
  await expect(page.getByRole('heading', { name: 'No recent relief work' })).toBeVisible()
})

test('Team Board detail failure preserves the core answer', async ({ page }) => {
  await installApiFixtures(page, { detailsFailure: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  await expect(page.getByRole('heading', { name: 'Recent Usage unavailable' })).toBeVisible()
})

test('Team Board share disclosure uses native controls and returns focus on Escape', async ({ page }) => {
  await installApiFixtures(page)
  await page.goto('/bullpen?team=BOS')
  const trigger = page.getByRole('button', { name: 'Open evidence sharing options' })
  await trigger.click()
  await expect(page.getByRole('button', { name: 'Copy published link' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
})

test('Pitcher, matchup, and history direct entries retain primary identities', async ({ page }) => {
  await installApiFixtures(page)
  await page.goto('/pitcher/101')
  await expect(page.getByRole('heading', { level: 1, name: 'Fixture Reliever' })).toBeVisible()
  await page.goto('/matchup/999')
  await expect(page.getByRole('heading', { level: 1, name: 'New York Yankees at Boston Red Sox' })).toBeVisible()
  await page.goto('/history/team/BOS')
  await expect(page.getByRole('heading', { level: 1, name: 'Boston Red Sox Team State History' })).toBeVisible()
})

test('share artifact remains readable with native evidence and destination links', async ({ page }) => {
  await installApiFixtures(page)
  await page.goto('/share/fixture-share')
  await expect(page.getByRole('heading', { level: 1, name: 'Fresh' })).toBeVisible()
  await expect(page.getByText('Rested options')).toBeVisible()
  await expect(page.getByRole('link', { name: /Open current Boston Red Sox bullpen board/ })).toBeVisible()
  await expect(page.locator('[role="table"]')).toHaveCount(0)
})

test('invalid route and invalid share provide readable recovery destinations', async ({ page }) => {
  await installApiFixtures(page)
  await page.goto('/not-a-real-route')
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible()
  await page.goto('/share/not-found')
  await expect(page.getByRole('heading', { level: 1, name: 'Shared artifact not found' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Return to BaseballOS' })).toBeVisible()
})

test('global crash fallback focuses an assertive readable recovery state', async ({ page }) => {
  let teamRequests = 0
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/bullpen/teams') teamRequests += 1
  })
  await installApiFixtures(page, { corruptTeams: true })
  await page.goto('/bullpen?view=pitchers')
  const alert = page.getByRole('alert')
  await expect(alert).toBeFocused()
  await expect(page.getByRole('heading', { level: 1, name: /Something went wrong/ })).toBeVisible()
  const reload = page.getByRole('button', { name: 'Reload' })
  await reload.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => teamRequests).toBeGreaterThan(1)
  await expect(page.getByRole('alert')).toBeFocused()
})

test('primary success routes have no uncaught errors or error-level console output', async ({ page }) => {
  const issues = []
  page.on('pageerror', error => issues.push(`pageerror: ${error.message}`))
  page.on('console', message => {
    if (message.type() === 'error') issues.push(`console: ${message.text()}`)
  })
  await installApiFixtures(page)
  for (const path of ['/', '/dashboard', '/search', '/bullpen?view=pitchers', '/bullpen?team=BOS', '/pitcher/101', '/matchup/999', '/history/team/BOS', '/share/fixture-share']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  }
  expect(issues).toEqual([])
})

test('primary public routes do not overflow at 390 by 844', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await installApiFixtures(page)
  for (const path of ['/', '/dashboard', '/bullpen?view=pitchers', '/bullpen?team=BOS', '/pitcher/101', '/matchup/999', '/history/team/BOS', '/share/fixture-share']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expectNoPageOverflow(page)
  }
})

test('desktop composition remains bounded and uses the available canvas', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await installApiFixtures(page)
  await page.goto('/dashboard')
  const main = await page.locator('#main-content').boundingBox()
  expect(main.width).toBeGreaterThan(1000)
  await expectNoPageOverflow(page)
})

test('200 percent equivalent reflow keeps navigation and labels reachable', async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 900 })
  await installApiFixtures(page)
  await page.goto('/bullpen?view=pitchers')
  await page.locator('html').evaluate(element => { element.style.fontSize = '200%' })
  await expect(page.getByRole('heading', { level: 1, name: 'Reliever Finder' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open navigation menu' })).toBeVisible()
  await expectNoPageOverflow(page)
})

test('reduced-motion preference disables nonessential movement', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await installApiFixtures(page)
  await page.goto('/')
  const motion = await page.evaluate(() => {
    const element = document.createElement('div')
    element.className = 'animate-pulse transition-all'
    document.body.appendChild(element)
    const style = getComputedStyle(element)
    const result = { animationDuration: style.animationDuration, transitionDuration: style.transitionDuration }
    element.remove()
    return result
  })
  expect(Number.parseFloat(motion.animationDuration)).toBeLessThanOrEqual(0.00001)
  expect(Number.parseFloat(motion.transitionDuration)).toBeLessThanOrEqual(0.00001)
})

test('major routes pass an automated WCAG AA scan', async ({ page }) => {
  await installApiFixtures(page)
  for (const path of ['/search', '/dashboard', '/bullpen?team=BOS', '/pitcher/101', '/share/fixture-share', '/methodology', '/trust']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()
    expect(results.violations, `${path}: ${results.violations.map(item => item.id).join(', ')}`).toEqual([])
  }
})

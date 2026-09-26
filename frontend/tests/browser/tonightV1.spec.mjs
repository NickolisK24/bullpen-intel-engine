import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {
  productionPayload,
  quietPayload,
  stressPayload,
  unavailablePayload,
} from '../fixtures/tonightV1Fixtures.mjs'

const TONIGHT_REQUEST = '/api/bullpen/intelligence/tonight?contract=tonight_v1'
const VIEWPORTS = [390, 430, 768, 1024, 1280, 1440, 1920]
const SCREENSHOT_WIDTHS = new Set([390, 768, 1440])

// Mocks every /api/** call. Only the tonight_v1 read is answered; anything
// else is recorded so the one-request contract can be asserted.
async function installTonightFixture(page, {
  body = productionPayload(),
  status = 200,
  failures = 0,
  hold = null,
} = {}) {
  const requests = []
  let remainingFailures = failures
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    requests.push(`${url.pathname}${url.search}`)
    if (url.pathname.endsWith('/bullpen/intelligence/tonight') && url.searchParams.get('contract') === 'tonight_v1') {
      if (hold) await hold
      if (remainingFailures > 0) {
        remainingFailures -= 1
        await route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"unavailable"}' })
        return
      }
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{"error":"not mocked"}' })
  })
  return requests
}

// Page errors and console errors from the app. Third-party font transport
// failures (outside the app and outside Tonight) are not attributable to it.
function collectAppErrors(page) {
  const errors = []
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`))
  page.on('console', message => {
    if (message.type() !== 'error') return
    const source = message.location()?.url || ''
    if (/fonts\.(googleapis|gstatic)\.com/.test(source)) return
    errors.push(`console: ${message.text()}`)
  })
  return errors
}

async function expectNoPageOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
}

async function expectNoTonightElementOverflow(page) {
  const overflowing = await page.evaluate(() => [...document.querySelectorAll('[data-testid="tonight-page"] *')]
    .filter(el => el.clientWidth > 0 && getComputedStyle(el).overflowX === 'visible' && el.scrollWidth > el.clientWidth + 1)
    .map(el => el.getAttribute('data-testid') || el.tagName))
  expect(overflowing).toEqual([])
}

async function expectAxeClean(page) {
  const accessibility = await new AxeBuilder({ page }).include('main').analyze()
  expect(accessibility.violations).toEqual([])
}

async function pksIn(page, testId) {
  return page.getByTestId(testId).getByTestId('tonight-game-card')
    .evaluateAll(nodes => nodes.map(node => Number(node.getAttribute('data-game-pk'))))
}

for (const width of VIEWPORTS) {
  test(`TN-09 17-game stress edition at ${width}px: layout, order, axe, one request`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = collectAppErrors(page)
    const payload = stressPayload()
    const requests = await installTonightFixture(page, { body: payload })
    await page.goto('/tonight')

    await expect(page.getByRole('heading', { level: 1, name: 'Tonight in MLB Bullpens' })).toBeVisible()
    await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
    await expect(page.getByTestId('tonight-featured').getByTestId('tonight-game-card')).toHaveCount(4)
    await expect(page.getByTestId('tonight-change')).toHaveCount(12)

    // TN-11.5: mounted slate cards follow lifecycle groups in backend order;
    // the two final games sit behind the collapsed Completed Games (2).
    const byStates = (states) => payload.games.filter(game => states.includes(game.state)).map(game => game.game_pk)
    expect(await pksIn(page, 'tonight-slate')).toEqual([
      ...byStates(['live', 'suspended']),
      ...byStates(['scheduled', 'uncertain', 'postponed']),
    ])
    await expect(page.getByRole('heading', { level: 3, name: 'Completed Games (2)' })).toBeVisible()
    expect(await pksIn(page, 'tonight-featured')).toEqual(payload.featured_game_pks)
    const changeHeadlines = await page.getByTestId('tonight-change').evaluateAll(nodes => nodes.map(node => node.querySelector('p.text-sm')?.textContent))
    expect(changeHeadlines).toEqual(payload.league_changes.map(change => change.headline))

    await expectNoPageOverflow(page)
    await expectNoTonightElementOverflow(page)
    const smallTargets = await page.evaluate(() => [...document.querySelectorAll('[data-testid="tonight-page"] a, [data-testid="tonight-page"] button')]
      .filter(el => el.getBoundingClientRect().height < 44)
      .map(el => el.textContent.trim()))
    expect(smallTargets).toEqual([])
    await expectAxeClean(page)

    expect(requests).toEqual([TONIGHT_REQUEST])
    expect(errors).toEqual([])
    if (SCREENSHOT_WIDTHS.has(width)) {
      await testInfo.attach(`tonight-full-${width}`, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
    }
  })
}

test('TN-09 card action rows share one baseline across a desktop row', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await installTonightFixture(page, { body: stressPayload() })
  await page.goto('/tonight')
  const rows = page.getByTestId('tonight-slate').getByTestId('tonight-card-actions')
  const first = await rows.nth(0).boundingBox()
  const second = await rows.nth(1).boundingBox()
  expect(Math.abs(first.y + first.height - (second.y + second.height))).toBeLessThanOrEqual(1)
})

test('TN-09 quiet day, quiet day with changes, and unavailable are calm status states', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 })
  const quiet = await installTonightFixture(page, { body: quietPayload() })
  await page.goto('/tonight')
  await expect(page.getByRole('status').filter({ hasText: "No MLB games are on tonight's slate." })).toBeVisible()
  await expect(page.getByTestId('tonight-date')).toBeVisible()
  await expect(page.getByTestId('tonight-changes')).toHaveCount(0)
  await expectNoPageOverflow(page)
  await expectAxeClean(page)
  expect(quiet).toEqual([TONIGHT_REQUEST])
  await testInfo.attach('tonight-quiet-390', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })

  await page.unroute('**/api/**')
  await installTonightFixture(page, { body: { ...quietPayload(), league_changes: stressPayload().league_changes.slice(0, 5) } })
  await page.reload()
  await expect(page.getByTestId('tonight-change')).toHaveCount(5)
  await expectAxeClean(page)

  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await page.unroute('**/api/**')
    await installTonightFixture(page, { body: unavailablePayload() })
    await page.reload()
    const state = page.getByTestId('tonight-unavailable')
    await expect(state).toHaveAttribute('role', 'status')
    await expect(state).toContainText("Tonight's trusted bullpen edition isn't available yet.")
    await expect(state).toContainText('Latest publication: Sep 26, 2026')
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByTestId('tonight-page').getByRole('button')).toHaveCount(0)
    await expect(page.getByTestId('tonight-game-card')).toHaveCount(0)
    await expectNoPageOverflow(page)
    await expectAxeClean(page)
    await testInfo.attach(`tonight-unavailable-${width}`, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
  }
})

test('TN-09 error retry fires once per activation and keeps focus on the page heading', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 })
  const errors = collectAppErrors(page)
  const requests = await installTonightFixture(page, { failures: 2 })
  await page.goto('/tonight')
  const alert = page.getByRole('alert')
  await expect(alert).toContainText("Tonight's bullpen view couldn't be loaded.")
  await expectAxeClean(page)
  expect(requests).toEqual([TONIGHT_REQUEST])

  // Two activations in the same task still issue exactly one retry request.
  await page.getByRole('button', { name: 'Try again' }).evaluate(button => { button.click(); button.click() })
  await expect(page.getByRole('alert')).toBeVisible()
  expect(requests).toEqual([TONIGHT_REQUEST, TONIGHT_REQUEST])
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused()

  // Keyboard activation: the next response succeeds and nothing re-polls.
  await page.getByRole('button', { name: 'Try again' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(14)
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
  await page.waitForTimeout(500)
  expect(requests).toEqual([TONIGHT_REQUEST, TONIGHT_REQUEST, TONIGHT_REQUEST])
  expect(errors.filter(line => !/503|Service Unavailable|\[API\]/.test(line))).toEqual([])
})

test('TN-09 loading shows shape-only skeletons, keeps the heading, and settles with low layout shift', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 })
  let release
  const hold = new Promise(resolve => { release = resolve })
  await page.addInitScript(() => {
    window.__tonightShift = 0
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.__tonightShift += entry.value
      }
    }).observe({ type: 'layout-shift', buffered: true })
  })
  const requests = await installTonightFixture(page, { body: stressPayload(), hold })
  await page.goto('/tonight')
  const loading = page.getByTestId('tonight-loading')
  await expect(loading).toHaveAttribute('aria-busy', 'true')
  await expect(page.getByRole('heading', { level: 1, name: 'Tonight in MLB Bullpens' })).toBeVisible()
  const visibleLoadingText = await loading.evaluate(node => [...node.querySelectorAll('[aria-hidden="true"]')].map(el => el.textContent).join('').trim())
  expect(visibleLoadingText).toBe('')
  await expect(page.getByTestId('tonight-quiet')).toHaveCount(0)
  await expect(page.getByTestId('tonight-unavailable')).toHaveCount(0)
  await expectAxeClean(page)

  const released = Date.now()
  release()
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  const renderMs = Date.now() - released
  await expect(loading).toHaveCount(0)
  const shift = await page.evaluate(() => window.__tonightShift)
  expect(shift).toBeLessThan(0.1)
  expect(renderMs).toBeLessThan(2000)
  // Settled page: no rerender loop keeps mutating the DOM.
  const mutations = await page.evaluate(() => new Promise(resolve => {
    let count = 0
    const observer = new MutationObserver(records => { count += records.length })
    observer.observe(document.querySelector('[data-testid="tonight-page"]'), { subtree: true, childList: true, attributes: true, characterData: true })
    setTimeout(() => { observer.disconnect(); resolve(count) }, 750)
  }))
  expect(mutations).toBe(0)
  test.info().annotations.push({ type: 'perf', description: `render after data: ${renderMs}ms; CLS ${shift.toFixed(4)}` })
  expect(requests).toEqual([TONIGHT_REQUEST])
})

test('TN-09 keyboard order follows visual order with visible focus and no traps', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await installTonightFixture(page, { body: stressPayload() })
  await page.goto('/tonight')
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)

  const expected = await page.evaluate(() => [...document.querySelectorAll('[data-testid="tonight-page"] a[href], [data-testid="tonight-page"] button')]
    .map(el => `${el.getAttribute('href')}|${el.getAttribute('aria-label') || el.textContent.trim()}`))
  await page.getByRole('heading', { level: 1 }).focus()
  const visited = []
  for (let i = 0; i < expected.length; i += 1) {
    await page.keyboard.press('Tab')
    const focus = await page.evaluate(() => {
      const el = document.activeElement
      const style = getComputedStyle(el)
      return {
        inside: Boolean(el.closest('[data-testid="tonight-page"]')),
        key: `${el.getAttribute('href')}|${el.getAttribute('aria-label') || el.textContent.trim()}`,
        ring: style.boxShadow !== 'none' || (style.outlineStyle !== 'none' && style.outlineWidth !== '0px'),
      }
    })
    expect(focus.inside).toBe(true)
    expect(focus.ring).toBe(true)
    visited.push(focus.key)
  }
  expect(visited).toEqual(expected)
  expect(new Set(visited.filter(key => key.includes('Team Board'))).size).toBeGreaterThan(1)
  await page.keyboard.press('Tab')
  expect(await page.evaluate(() => Boolean(document.activeElement.closest('[data-testid="tonight-page"]')))).toBe(false)
})

test('TN-09 200% zoom, text-spacing stress, and reduced motion stay usable', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await installTonightFixture(page, { body: stressPayload() })

  await page.setViewportSize({ width: 720, height: 900 })
  await page.goto('/tonight')
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  await page.locator('html').evaluate(element => { element.style.fontSize = '200%' })
  await expectNoPageOverflow(page)
  await expectNoTonightElementOverflow(page)

  await page.setViewportSize({ width: 390, height: 900 })
  await page.locator('html').evaluate(element => { element.style.fontSize = '' })
  await page.addStyleTag({ content: '* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }' })
  await expectNoPageOverflow(page)
  await expectNoTonightElementOverflow(page)

  const transition = await page.locator('[data-link="matchup"]').first().evaluate(el => getComputedStyle(el).transitionDuration)
  expect(Number.parseFloat(transition)).toBeLessThanOrEqual(0.00001)
})

test('TN-09 direct entry, refresh, and handoff links reach their destinations', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 })
  const requests = await installTonightFixture(page)
  await page.goto('/tonight')
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(14)
  await page.reload()
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(14)
  expect(requests).toEqual([TONIGHT_REQUEST, TONIGHT_REQUEST])

  const payload = productionPayload()
  // games[0] is scheduled, so it is mounted in Upcoming (lifecycle grouping).
  const card = page.getByTestId('tonight-slate').locator(`[data-game-pk="${payload.games[0].game_pk}"]`)
  await expect(card.locator('[data-link="team-board"]').nth(0)).toHaveAttribute('href', payload.games[0].links.away_team_board)
  await expect(card.locator('[data-link="team-board"]').nth(1)).toHaveAttribute('href', payload.games[0].links.home_team_board)
  await expect(card.locator('[data-link="matchup"]')).toHaveAttribute('href', payload.games[0].links.matchup)
  const leadGame = payload.games.find(game => game.game_pk === payload.lead.game_pk)
  await expect(page.locator('[data-link="lead-matchup"]')).toHaveAttribute('href', leadGame.links.matchup)

  await card.locator('[data-link="matchup"]').click()
  await expect(page).toHaveURL(new RegExp(`${payload.games[0].links.matchup}$`))
  await page.goBack()
  await expect(page).toHaveURL(/\/tonight$/)
  await page.getByTestId('tonight-slate').locator(`[data-game-pk="${payload.games[0].game_pk}"]`).locator('[data-link="team-board"]').first().click()
  await expect(page).toHaveURL(/\/bullpen\?view=board&team=NYY$/)
})

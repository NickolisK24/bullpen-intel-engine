import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {
  productionPayload,
  quietPayload,
  unavailablePayload,
} from '../fixtures/tonightV1Fixtures.mjs'

// Mocks every /api/** call. Only the tonight_v1 read is answered; anything
// else is recorded so the one-request contract can be asserted.
async function installTonightFixture(page, { body = productionPayload(), status = 200, failFirst = false } = {}) {
  const requests = []
  let failures = failFirst ? 1 : 0
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    requests.push(`${url.pathname}${url.search}`)
    if (url.pathname.endsWith('/bullpen/intelligence/tonight') && url.searchParams.get('contract') === 'tonight_v1') {
      if (failures > 0) {
        failures -= 1
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

async function expectNoPageOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
}

for (const width of [390, 768, 1440]) {
  test(`TN-08 /tonight renders a 15-game edition at ${width}px with one API request`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const pageErrors = []
    page.on('pageerror', error => pageErrors.push(error.message))
    const requests = await installTonightFixture(page)
    await page.goto('/tonight')

    await expect(page.getByRole('heading', { level: 1, name: 'Tonight in MLB Bullpens' })).toBeVisible()
    await expect(page.getByTestId('tonight-lead')).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'Games to Watch' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: "Tonight's Slate" })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'What Changed' })).toBeVisible()
    await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
    await expect(page.getByTestId('tonight-featured').getByTestId('tonight-game-card')).toHaveCount(3)

    const payload = productionPayload()
    const slatePks = await page.getByTestId('tonight-slate').getByTestId('tonight-game-card')
      .evaluateAll(nodes => nodes.map(node => Number(node.getAttribute('data-game-pk'))))
    expect(slatePks).toEqual(payload.games.map(game => game.game_pk))
    const featuredPks = await page.getByTestId('tonight-featured').getByTestId('tonight-game-card')
      .evaluateAll(nodes => nodes.map(node => Number(node.getAttribute('data-game-pk'))))
    expect(featuredPks).toEqual(payload.featured_game_pks)

    await expectNoPageOverflow(page)
    const accessibility = await new AxeBuilder({ page }).include('main').analyze()
    expect(accessibility.violations).toEqual([])

    expect(requests).toEqual(['/api/bullpen/intelligence/tonight?contract=tonight_v1'])
    await expect(page).toHaveURL(/\/tonight$/)
    expect(pageErrors).toEqual([])
  })
}

test('TN-08 /tonight quiet day and unavailable edition states', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 })
  await installTonightFixture(page, { body: quietPayload() })
  await page.goto('/tonight')
  await expect(page.getByText("No MLB games are on tonight's slate.")).toBeVisible()
  await expectNoPageOverflow(page)
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])

  await page.unroute('**/api/**')
  await installTonightFixture(page, { body: unavailablePayload() })
  await page.reload()
  await expect(page.getByText("Tonight's trusted bullpen edition isn't available yet.")).toBeVisible()
  await expect(page.getByText('Latest publication: Sep 26, 2026')).toBeVisible()
  await expect(page.getByTestId('tonight-game-card')).toHaveCount(0)
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})

test('TN-08 /tonight network error offers retry without any fallback request', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 })
  const requests = await installTonightFixture(page, { failFirst: true })
  await page.goto('/tonight')
  await expect(page.getByRole('alert')).toContainText("Tonight's bullpen view couldn't be loaded.")
  expect(requests).toEqual(['/api/bullpen/intelligence/tonight?contract=tonight_v1'])
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])

  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  expect(requests).toEqual([
    '/api/bullpen/intelligence/tonight?contract=tonight_v1',
    '/api/bullpen/intelligence/tonight?contract=tonight_v1',
  ])
})

test('TN-08 /tonight game card links reach Team Board and Matchup routes by keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await installTonightFixture(page)
  await page.goto('/tonight')
  const card = page.getByTestId('tonight-slate').getByTestId('tonight-game-card').first()
  const payload = productionPayload()
  await expect(card.locator('[data-link="team-board"]').first()).toHaveAttribute('href', payload.games[0].links.away_team_board)
  await expect(card.locator('[data-link="team-board"]').nth(1)).toHaveAttribute('href', payload.games[0].links.home_team_board)
  await expect(card.locator('[data-link="matchup"]')).toHaveAttribute('href', payload.games[0].links.matchup)
  await card.locator('[data-link="matchup"]').focus()
  await expect(card.locator('[data-link="matchup"]')).toBeFocused()
})

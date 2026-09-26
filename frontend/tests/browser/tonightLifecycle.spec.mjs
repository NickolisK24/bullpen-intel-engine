import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { allFinalPayload, mixedLifecyclePayload } from '../fixtures/tonightV1Fixtures.mjs'

const TONIGHT_REQUEST = '/api/bullpen/intelligence/tonight?contract=tonight_v1'

async function installTonightFixture(page, body) {
  const requests = []
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    requests.push(`${url.pathname}${url.search}`)
    if (url.pathname.endsWith('/bullpen/intelligence/tonight') && url.searchParams.get('contract') === 'tonight_v1') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{"error":"not mocked"}' })
  })
  return requests
}

function collectAppErrors(page) {
  const errors = []
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`))
  page.on('console', message => {
    if (message.type() !== 'error') return
    if (/fonts\.(googleapis|gstatic)\.com/.test(message.location()?.url || '')) return
    errors.push(`console: ${message.text()}`)
  })
  return errors
}

async function expectNoPageOverflow(page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1)
}

const axeClean = async (page) => expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
const cardPks = (locator) => locator.getByTestId('tonight-game-card')
  .evaluateAll(nodes => nodes.map(node => Number(node.getAttribute('data-game-pk'))))
const pksWhere = (payload, states) => payload.games.filter(game => states.includes(game.state)).map(game => game.game_pk)

for (const width of [390, 768, 1440]) {
  test(`TN-11.5 mixed slate at ${width}px: lifecycle groups, collapsed completed, keyboard disclosure`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = collectAppErrors(page)
    const payload = mixedLifecyclePayload()
    const requests = await installTonightFixture(page, payload)
    await page.goto('/')

    const slate = page.getByTestId('tonight-slate')
    await expect(slate.getByRole('heading', { level: 3, name: 'In Progress' })).toBeVisible()
    await expect(slate.getByRole('heading', { level: 3, name: 'Upcoming' })).toBeVisible()
    await expect(slate.getByRole('heading', { level: 3, name: 'Completed Games (7)' })).toBeVisible()
    expect(await cardPks(page.getByTestId('tonight-slate-in-progress'))).toEqual(pksWhere(payload, ['live', 'suspended']))
    expect(await cardPks(page.getByTestId('tonight-slate-upcoming'))).toEqual(pksWhere(payload, ['scheduled', 'uncertain', 'postponed']))
    const completed = page.getByTestId('tonight-slate-completed')
    await expect(completed.getByTestId('tonight-game-card')).toHaveCount(0)
    await expect(page.getByTestId('tonight-featured').getByTestId('tonight-game-card')).toHaveCount(4)

    const toggle = page.getByRole('button', { name: 'Show completed games' })
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    const controls = await toggle.getAttribute('aria-controls')
    await expect(page.locator(`#${controls}`)).toHaveCount(1)
    await expectNoPageOverflow(page)
    await axeClean(page)

    await toggle.focus()
    await page.keyboard.press('Enter')
    const hide = page.getByRole('button', { name: 'Hide completed games' })
    await expect(hide).toHaveAttribute('aria-expanded', 'true')
    await expect(hide).toBeFocused()
    expect(await cardPks(completed)).toEqual(pksWhere(payload, ['final']))
    await expect(completed.getByTestId('tonight-game-status').first()).toHaveText('Final')
    await expectNoPageOverflow(page)
    await axeClean(page)

    await page.keyboard.press('Space')
    await expect(page.getByRole('button', { name: 'Show completed games' })).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByRole('button', { name: 'Show completed games' })).toBeFocused()
    await expect(completed.getByTestId('tonight-game-card')).toHaveCount(0)

    expect(requests).toEqual([TONIGHT_REQUEST])
    expect(errors).toEqual([])
  })

  test(`TN-11.5 all-final slate at ${width}px: compact completed state and full access on expand`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = collectAppErrors(page)
    const payload = allFinalPayload()
    const requests = await installTonightFixture(page, payload)
    await page.goto('/tonight')

    const slate = page.getByTestId('tonight-slate')
    await expect(slate.getByTestId('tonight-all-final')).toHaveText("All of tonight's games are complete.")
    await expect(slate.getByRole('heading', { level: 3, name: 'Completed Games (17)' })).toBeVisible()
    await expect(slate.getByTestId('tonight-game-card')).toHaveCount(0)
    await expect(page.getByTestId('tonight-lead')).toBeVisible()
    await expect(page.getByTestId('tonight-changes')).toBeVisible()
    const collapsedHeight = await page.evaluate(() => document.documentElement.scrollHeight)
    await expectNoPageOverflow(page)
    await axeClean(page)

    await page.getByRole('button', { name: 'Show completed games' }).click()
    await expect(slate.getByTestId('tonight-game-card')).toHaveCount(17)
    expect(await cardPks(slate)).toEqual(payload.games.map(game => game.game_pk))
    const expandedHeight = await page.evaluate(() => document.documentElement.scrollHeight)
    await expectNoPageOverflow(page)
    await axeClean(page)

    const first = slate.getByTestId('tonight-game-card').first()
    await expect(first.locator('[data-link="team-board"]').nth(0)).toHaveAttribute('href', payload.games[0].links.away_team_board)
    await expect(first.locator('[data-link="team-board"]').nth(1)).toHaveAttribute('href', payload.games[0].links.home_team_board)
    await expect(first.locator('[data-link="matchup"]')).toHaveAttribute('href', payload.games[0].links.matchup)

    const reduction = Math.round((1 - collapsedHeight / expandedHeight) * 1000) / 10
    testInfo.annotations.push({ type: 'page-height', description: `${width}px collapsed ${collapsedHeight}px, expanded ${expandedHeight}px, reduction ${reduction}%` })
    expect(collapsedHeight).toBeLessThan(expandedHeight * 0.7)
    expect(requests).toEqual([TONIGHT_REQUEST])
    expect(errors).toEqual([])

    await first.locator('[data-link="matchup"]').click()
    await expect(page).toHaveURL(new RegExp(`${payload.games[0].links.matchup}$`))
  })
}

test('TN-11.5 collapsed completed cards are never tab stops', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await installTonightFixture(page, mixedLifecyclePayload())
  await page.goto('/')
  await expect(page.getByTestId('tonight-slate-upcoming').getByTestId('tonight-game-card').first()).toBeVisible()
  const reachable = await page.evaluate(() => [...document.querySelectorAll('[data-testid="tonight-slate-completed"] a, [data-testid="tonight-slate-completed"] button')]
    .map(el => el.textContent.trim()))
  expect(reachable).toEqual(['Show completed games'])
})

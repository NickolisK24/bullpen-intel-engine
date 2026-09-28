import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { allFinalFeaturedPayload, lateNightFeaturedPayload } from '../fixtures/tonightV1Fixtures.mjs'

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

for (const width of [390, 768, 1440]) {
  test(`TN-11.6 A: 1 non-final + 3 final featured at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = collectAppErrors(page)
    const payload = lateNightFeaturedPayload()
    const uncertainPk = payload.games.find(game => game.state === 'uncertain').game_pk
    const finalFeatured = payload.featured_game_pks.filter(pk => pk !== uncertainPk)
    const requests = await installTonightFixture(page, payload)
    await page.goto('/')

    const featured = page.getByTestId('tonight-featured')
    await expect(featured.getByRole('heading', { level: 2, name: 'Games to Watch' })).toBeVisible()
    expect(await cardPks(featured)).toEqual([uncertainPk])
    expect(await cardPks(page.getByTestId('tonight-slate-upcoming'))).toEqual([uncertainPk])
    await expect(page.getByRole('heading', { level: 3, name: 'Completed Games (14)' })).toBeVisible()
    await expect(page.getByTestId('tonight-slate-completed').getByTestId('tonight-game-card')).toHaveCount(0)

    const card = featured.getByTestId('tonight-game-card')
    const game = payload.games.find(g => g.game_pk === uncertainPk)
    await expect(card.locator('[data-link="team-board"]').nth(0)).toHaveAttribute('href', game.links.away_team_board)
    await expect(card.locator('[data-link="team-board"]').nth(1)).toHaveAttribute('href', game.links.home_team_board)
    await expect(card.locator('[data-link="matchup"]')).toHaveAttribute('href', game.links.matchup)

    await expectNoPageOverflow(page)
    await axeClean(page)
    const collapsedHeight = await page.evaluate(() => document.documentElement.scrollHeight)
    testInfo.annotations.push({ type: 'page-height', description: `late-night ${width}px collapsed ${collapsedHeight}px` })

    await page.getByRole('button', { name: 'Show completed games' }).click()
    const completed = await cardPks(page.getByTestId('tonight-slate-completed'))
    expect(completed).toHaveLength(14)
    for (const pk of finalFeatured) expect(completed).toContain(pk)
    await axeClean(page)

    // Tonight made exactly one request; the Matchup page may fetch its own data.
    expect(requests).toEqual([TONIGHT_REQUEST])
    expect(errors).toEqual([])
    await featured.getByTestId('tonight-game-card').locator('[data-link="matchup"]').click()
    await expect(page).toHaveURL(new RegExp(`${game.links.matchup}$`))
  })

  test(`TN-11.6 B: all 4 featured final at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = collectAppErrors(page)
    const payload = allFinalFeaturedPayload()
    const requests = await installTonightFixture(page, payload)
    await page.goto('/tonight')

    await expect(page.getByTestId('tonight-slate').getByTestId('tonight-all-final')).toBeVisible()
    await expect(page.getByTestId('tonight-featured')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Games to Watch' })).toHaveCount(0)
    await expect(page.getByRole('heading', { level: 3, name: 'Completed Games (15)' })).toBeVisible()
    await expectNoPageOverflow(page)
    await axeClean(page)

    await page.getByRole('button', { name: 'Show completed games' }).click()
    const completed = await cardPks(page.getByTestId('tonight-slate-completed'))
    expect(completed).toEqual(payload.games.map(game => game.game_pk))
    for (const pk of payload.featured_game_pks) expect(completed).toContain(pk)
    const first = page.getByTestId('tonight-slate-completed').getByTestId('tonight-game-card').first()
    await expect(first.locator('[data-link="team-board"]').first()).toHaveAttribute('href', payload.games[0].links.away_team_board)
    await expectNoPageOverflow(page)
    await axeClean(page)
    expect(requests).toEqual([TONIGHT_REQUEST])
    expect(errors).toEqual([])
  })
}

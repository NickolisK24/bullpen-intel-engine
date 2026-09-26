import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {
  productionPayload,
  quietPayload,
  unavailablePayload,
} from '../fixtures/tonightV1Fixtures.mjs'

const TONIGHT_REQUEST = '/api/bullpen/intelligence/tonight?contract=tonight_v1'
const LEGACY_HOME_SELECTORS = ['#daily-edition', '#since-yesterday', '#bullpen-picture', '#explore-baseballos', '#audience-signup']

async function installTonightFixture(page, { body = productionPayload(), failures = 0 } = {}) {
  const requests = []
  let remaining = failures
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    requests.push(`${url.pathname}${url.search}`)
    if (url.pathname.endsWith('/bullpen/intelligence/tonight') && url.searchParams.get('contract') === 'tonight_v1') {
      if (remaining > 0) {
        remaining -= 1
        await route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"unavailable"}' })
        return
      }
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

async function tonightContent(page) {
  const pks = (testId) => page.getByTestId(testId).getByTestId('tonight-game-card')
    .evaluateAll(nodes => nodes.map(node => node.getAttribute('data-game-pk')))
  return {
    lead: await page.getByTestId('tonight-lead').innerText(),
    featured: await pks('tonight-featured'),
    slate: await pks('tonight-slate'),
    changes: await page.getByTestId('tonight-change').evaluateAll(nodes => nodes.map(node => node.querySelector('p.text-sm')?.textContent)),
    links: await page.locator('[data-testid="tonight-page"] a[data-link]').evaluateAll(nodes => nodes.map(node => node.getAttribute('href'))),
  }
}

const tonightNavItem = (page) => page.locator('#primary-navigation a.nav-item[href="/"]')

for (const width of [390, 768, 1440]) {
  test(`TN-10 / renders Tonight v1 at ${width}px with one request and no legacy Home`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = collectAppErrors(page)
    const requests = await installTonightFixture(page)
    await page.goto('/')

    await expect(page.getByRole('heading', { level: 1, name: 'Tonight in MLB Bullpens' })).toBeVisible()
    await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
    await expect(page.getByTestId('tonight-lead')).toBeVisible()
    await expect(page.getByTestId('tonight-featured')).toBeVisible()
    await expect(page.getByTestId('tonight-changes')).toBeVisible()
    await expect(page).toHaveTitle('BaseballOS | Tonight in MLB Bullpens')
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://baseballos.app/')
    for (const selector of LEGACY_HOME_SELECTORS) await expect(page.locator(selector)).toHaveCount(0)
    await expect(page.getByText('Daily Edition')).toHaveCount(0)
    await expect(page.getByText('Since Yesterday')).toHaveCount(0)

    await expect(tonightNavItem(page)).toHaveAttribute('aria-current', 'page')
    await expect(tonightNavItem(page)).toContainText('Tonight')
    await expect(page.locator('#primary-navigation a[aria-current="page"]')).toHaveCount(1)

    await expectNoPageOverflow(page)
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
    expect(requests).toEqual([TONIGHT_REQUEST])
    expect(errors).toEqual([])
  })
}

test('TN-10 / and /tonight render equivalent Tonight content and both mark Tonight active', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const requests = await installTonightFixture(page)
  await page.goto('/')
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  const root = await tonightContent(page)

  await page.goto('/tonight')
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  const alias = await tonightContent(page)
  expect(alias).toEqual(root)
  expect(root.slate).toEqual(productionPayload().games.map(game => String(game.game_pk)))
  await expect(tonightNavItem(page)).toHaveAttribute('aria-current', 'page')
  await expect(page).toHaveTitle('BaseballOS | Tonight in MLB Bullpens')
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://baseballos.app/')
  expect(requests).toEqual([TONIGHT_REQUEST, TONIGHT_REQUEST])
})

test('TN-10 /today redirects to / once and renders Tonight', async ({ page }) => {
  const requests = await installTonightFixture(page)
  await page.goto('/today')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  expect(requests).toEqual([TONIGHT_REQUEST])
})

test('TN-10 direct refresh of / and /tonight, brand link, and in-app nav keep one request per page', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const requests = await installTonightFixture(page)
  await page.goto('/')
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  await page.reload()
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  await page.goto('/tonight')
  await page.reload()
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  expect(requests).toEqual(Array(4).fill(TONIGHT_REQUEST))

  // Brand returns to / from another route; the nav Tonight item does too.
  await page.getByTestId('tonight-slate').getByTestId('tonight-game-card').first().locator('[data-link="matchup"]').click()
  await expect(page).toHaveURL(/\/matchup\/\d+$/)
  await page.getByTestId('brand-home-link').click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Tonight in MLB Bullpens' })).toBeVisible()
  await page.locator('#primary-navigation a[href="/dashboard"]').click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await tonightNavItem(page).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  const tonightRequests = requests.filter(entry => entry.includes('/intelligence/tonight'))
  expect(tonightRequests.every(entry => entry === TONIGHT_REQUEST)).toBe(true)
})

test('TN-10 mobile menu reaches Tonight by keyboard with an accurate active state', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 })
  await installTonightFixture(page)
  await page.goto('/dashboard')
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  const item = tonightNavItem(page)
  await expect(item).toBeVisible()
  await expect(item).not.toHaveAttribute('aria-current', 'page')
  await item.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Tonight in MLB Bullpens' })).toBeVisible()
  await expect(tonightNavItem(page)).toHaveAttribute('aria-current', 'page')
})

test('TN-10 root unavailable, quiet day and error/retry states', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 })
  await installTonightFixture(page, { body: unavailablePayload() })
  await page.goto('/')
  await expect(page.getByTestId('tonight-unavailable')).toContainText("Tonight's trusted bullpen edition isn't available yet.")
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])

  await page.unroute('**/api/**')
  await installTonightFixture(page, { body: quietPayload() })
  await page.reload()
  await expect(page.getByTestId('tonight-quiet')).toContainText("No MLB games are on tonight's slate.")

  await page.unroute('**/api/**')
  const requests = await installTonightFixture(page, { failures: 1 })
  await page.reload()
  await expect(page.getByRole('alert')).toContainText("Tonight's bullpen view couldn't be loaded.")
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByTestId('tonight-slate').getByTestId('tonight-game-card')).toHaveCount(15)
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
  expect(requests).toEqual([TONIGHT_REQUEST, TONIGHT_REQUEST])
})

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

function teamBoardFixtureFor(teamId) {
  const team = teams.find(item => Number(item.team_id) === Number(teamId)) || teams[0]
  const nextIdentity = {
    ...teamBoardCore.publication_identity,
    team_id: team.team_id,
    team_abbreviation: team.team_abbreviation,
  }
  const pitcherId = team.team_id === 111 ? 101 : team.team_id * 1000 + 1
  const pitcherName = team.team_id === 111
    ? 'Fixture Reliever'
    : `${team.team_abbreviation} Fixture Reliever`
  const core = structuredClone(teamBoardCore)
  core.team = team
  core.publication_identity = nextIdentity
  if (team.team_id !== 111) {
    core.summary = `${team.team_name} has a current published bullpen read.`
    core.team_state.summary = core.summary
  }
  core.active_bullpen.arms[0].pitcher_id = pitcherId
  core.active_bullpen.arms[0].name = pitcherName
  core.operating_state.team = team

  const details = structuredClone(teamBoardDetails)
  details.publication_identity = nextIdentity
  details.recent_usage_rest.active_pitchers[0].pitcher_id = pitcherId
  details.recent_usage_rest.active_pitchers[0].pitcher_name = pitcherName
  const workload = details.workload_overview.frozen_team_workload
  workload.concentration_7_day.contributors[0].pitcher_id = pitcherId
  workload.concentration_7_day.contributors[0].name = pitcherName
  workload.concentration_7_day.top_contributor.pitcher_id = pitcherId
  workload.concentration_7_day.top_contributor.name = pitcherName
  workload.concentration_7_day.top_3_contributors[0].pitcher_id = pitcherId
  workload.concentration_7_day.top_3_contributors[0].name = pitcherName
  const deployment = details.roles_deployment.frozen_public_deployment
  deployment.team_id = team.team_id
  deployment.profiles[0].team_id = team.team_id
  deployment.profiles[0].pitcher_id = pitcherId
  deployment.profiles[0].pitcher_name = pitcherName
  deployment.profiles[0].observed_profile.pitcher_id = pitcherId
  deployment.profiles[0].context.pitcher_id = pitcherId
  const rotation = details.rotation_impact.frozen_recent_games
  rotation.team_id = team.team_id
  rotation.starts[0].starter_name = `${team.team_abbreviation} Fixture Starter`
  rotation.starts[0].starter_pitcher_id = team.team_id * 1000 + 500
  details.performance.metrics[0].value = team.team_abbreviation === 'NYY' ? '4.11'
    : team.team_abbreviation === 'LAD' ? '2.99' : '3.42'
  return { core, details, pitcherName }
}

async function installApiFixtures(page, {
  detailsFailure = false,
  detailsIdentityMismatch = false,
  deferDetails = false,
  partialCarrier = false,
  partialDeployment = false,
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
    const coreMatch = path.match(/^\/api\/bullpen\/teams\/(\d+)\/board-v2\/core$/)
    if (coreMatch) return json(teamBoardFixtureFor(Number(coreMatch[1])).core)
    const detailsMatch = path.match(/^\/api\/bullpen\/teams\/(\d+)\/board-v2\/details$/)
    if (detailsMatch) {
      const teamId = Number(detailsMatch[1])
      if (detailsGate && teamId === 111) await detailsGate
      const details = teamBoardFixtureFor(teamId).details
      if (partialCarrier) {
        details.recent_usage_rest.status = 'partial'
        details.recent_usage_rest.reason_code = 'some_usage_rest_fields_incomplete'
        details.recent_usage_rest.active_pitchers[0].high_pitch_outing = {
          value: null, status: 'unknown', reason_codes: ['appearance_pitch_count_unknown'], threshold: 25,
        }
        details.workload_overview.frozen_team_workload.windows.window_30.outs = {
          value: null, status: 'partial', reason_codes: ['slate_coverage_incomplete'],
        }
      }
      if (partialDeployment) {
        const context = details.roles_deployment.frozen_public_deployment.profiles[0].context
        context.entry_inning.status = 'partial'
        context.entry_inning.known_appearances = 3
        context.entry_inning.by_inning = [{ inning: 8, appearances: 1 }, { inning: 9, appearances: 2 }]
        context.entry_inning.eighth_or_later_appearances = 3
        context.score_context.status = 'unknown'
        context.score_context.known_appearances = 0
        context.score_context.leading = 0
        context.score_context.tied = 0
        context.score_context.trailing = 0
        context.leverage.status = 'unknown'
        context.leverage.known_appearances = 0
        context.leverage.high = 0
        context.leverage.middle = 0
        context.leverage.low = 0
      }
      return detailsFailure
        ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'fixture detail outage' }) })
        : json(detailsIdentityMismatch ? {
            ...details,
            publication_identity: {
              ...details.publication_identity,
              snapshot_id: details.publication_identity.snapshot_id + 1,
            },
          } : details)
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
  await expect(page.getByTestId('team-board-recent-usage')).toContainText('25+ pitch outing')
})

test('Team Board detail failure preserves the core answer', async ({ page }) => {
  await installApiFixtures(page, { detailsFailure: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  await expect(page.getByRole('heading', { name: 'Recent Usage unavailable' })).toBeVisible()
})

test('Team Board rejects mismatched details without replacing the core answer', async ({ page }) => {
  await installApiFixtures(page, { detailsIdentityMismatch: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  await expect(page.getByRole('heading', { name: 'Recent Usage unavailable' })).toBeVisible()
  await expect(page.getByText('Fixture Reliever').first()).toBeVisible()
})

test('Team Board keeps the answer and active bullpen readable at product breakpoints', async ({ page }) => {
  await installApiFixtures(page)
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/bullpen?team=BOS')
    await expect(page.getByTestId('team-board-answer-block')).toContainText('Boston Red Sox')
    await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
    await expect(page.getByTestId('team-board-active-bullpen')).toContainText('Fixture Reliever')
    await expect(page.getByTestId('team-board-recent-usage')).toContainText('Yesterday')
    await expect(page.getByTestId('team-board-recent-usage')).toContainText('3 Days')
    await expect(page.getByTestId('team-board-recent-usage')).toContainText('7 Days')
    await expectNoPageOverflow(page)
  }
})

test('Team Board recent usage journeys render BAL, LAD, and NYY publication-bound carriers', async ({ page }) => {
  await installApiFixtures(page)
  for (const abbreviation of ['BAL', 'LAD', 'NYY']) {
    await page.goto(`/bullpen?team=${abbreviation}`)
    await expect(page.getByTestId('team-board-answer-block')).toContainText(
      teams.find(team => team.team_abbreviation === abbreviation).team_name,
    )
    const recent = page.getByTestId('team-board-recent-usage')
    await expect(recent).toContainText(`${abbreviation} Fixture Reliever`)
    await expect(recent).toContainText('Back-to-back')
    await expect(recent).toContainText('25+ pitch outing')
    await expectNoPageOverflow(page)
  }
})

test('TB-04 four-window workload renders BAL, LAD, and NYY without overflow at product widths', async ({ page }) => {
  await installApiFixtures(page)
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const abbreviation of ['BAL', 'LAD', 'NYY']) {
      await page.goto(`/bullpen?team=${abbreviation}`)
      const workload = page.getByTestId('team-board-workload-overview')
      await expect(workload).toContainText(`${abbreviation} Fixture Reliever`)
      await expect(workload.getByRole('table', { name: 'Team relief workload by baseball-date window' })).toBeVisible()
      for (const days of [3, 7, 14, 30]) await expect(workload.locator(`[data-window-days="${days}"]`)).toBeVisible()
      await expect(workload).toContainText('Top 3 arms account for 80% of 7-day pitches')
      await expect(workload).toContainText('Recent off-active contributors:')
      await expectNoPageOverflow(page)
    }
  }
})

test('TB-04 preserves partial metric evidence without hiding complete windows', async ({ page }) => {
  await installApiFixtures(page, { partialCarrier: true })
  await page.goto('/bullpen?team=BOS')
  const workload = page.getByTestId('team-board-workload-overview')
  await expect(workload.locator('[data-window-days="30"]')).toContainText('partial')
  await expect(workload.locator('[data-window-days="30"]')).toContainText('430')
  await expect(workload.locator('[data-window-days="7"]')).toContainText('88')
  await expect(workload.locator('[data-window-days="3"]')).toContainText('0')
})

test('TB-04 is withheld on mismatched details while the core remains visible', async ({ page }) => {
  await installApiFixtures(page, { detailsIdentityMismatch: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  await expect(page.getByTestId('team-board-active-bullpen')).toContainText('Fixture Reliever')
  await expect(page.getByTestId('team-board-workload-overview')).not.toContainText('Top 3 arms account for')
})

test('TB-04 does not attach delayed old-team workload after switching', async ({ page }) => {
  const fixtures = await installApiFixtures(page, { deferDetails: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('workload-overview-skeleton')).toBeVisible()
  await page.getByLabel('Select team for Team Board').selectOption('147')
  const workload = page.getByTestId('team-board-workload-overview')
  await expect(workload).toContainText('NYY Fixture Reliever')
  fixtures.releaseDetails()
  await expect(workload).toContainText('NYY Fixture Reliever')
  await expect(workload.getByText('Fixture Reliever', { exact: true })).toHaveCount(0)
})

test('TB-05 serves frozen roles and deployment for BAL, LAD, and NYY at product widths', async ({ page }) => {
  await installApiFixtures(page)
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const abbreviation of ['BAL', 'LAD', 'NYY']) {
      await page.goto(`/bullpen?team=${abbreviation}`)
      const section = page.getByTestId('team-board-roles-deployment')
      await expect(section).toContainText(`${abbreviation} Fixture Reliever`)
      await expect(section).toContainText('Trusted Arm')
      await expect(section).toContainText('Inning 9: 2')
      await expect(section).toContainText('2 leading · 1 tied · 1 trailing')
      await expect(section).toContainText('2 high · 1 middle · 1 low')
      await expectNoPageOverflow(page)
    }
  }
})

test('TB-05 shows independent partial and unknown evidence while preserving factual saves', async ({ page }) => {
  await installApiFixtures(page, { partialDeployment: true })
  await page.goto('/bullpen?team=BOS')
  const section = page.getByTestId('team-board-roles-deployment')
  await expect(section).toContainText('partial, 3 of 4 known')
  await expect(section).toContainText('2 saves')
  await expect(section).not.toContainText('0 high · 0 middle · 0 low')
})

test('TB-05 rejects mismatched details without affecting TB-01 through TB-04', async ({ page }) => {
  await installApiFixtures(page, { detailsIdentityMismatch: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  await expect(page.getByTestId('team-board-active-bullpen')).toContainText('Fixture Reliever')
  await expect(page.getByTestId('team-board-roles-deployment')).not.toContainText('Inning 9: 2')
})

test('TB-05 discards delayed old-team deployment on team switch', async ({ page }) => {
  const fixtures = await installApiFixtures(page, { deferDetails: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('roles-deployment-skeleton')).toBeVisible()
  await page.getByLabel('Select team for Team Board').selectOption('147')
  const section = page.getByTestId('team-board-roles-deployment')
  await expect(section).toContainText('NYY Fixture Reliever')
  fixtures.releaseDetails()
  await expect(section).toContainText('NYY Fixture Reliever')
  await expect(section).not.toContainText('Fixture Reliever recorded')
})

test('TB-05 local fixture readiness is timed separately from core and details', async ({ page }) => {
  await installApiFixtures(page)
  const responseTimes = {}
  page.on('response', response => {
    const path = new URL(response.url()).pathname
    if (path.endsWith('/board-v2/core')) responseTimes.core = performance.now()
    if (path.endsWith('/board-v2/details')) responseTimes.details = performance.now()
  })
  const start = performance.now()
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  const coreReady = performance.now()
  await expect(page.getByTestId('team-board-roles-deployment')).toContainText('Inning 9: 2')
  const rolesReady = performance.now()
  expect(responseTimes.core).toBeDefined()
  expect(responseTimes.details).toBeDefined()
  console.log(`TB-05 local fixture: core=${Math.round(coreReady - start)}ms details-response=${Math.round(responseTimes.details - start)}ms roles-ready=${Math.round(rolesReady - start)}ms details-to-roles=${Math.round(rolesReady - responseTimes.details)}ms`)
})

test('TB-06 shows frozen ERA and WHIP at product widths across BAL, LAD, and NYY', async ({ page }) => {
  await installApiFixtures(page)
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const abbreviation of ['BAL', 'LAD', 'NYY']) {
      await page.goto(`/bullpen?team=${abbreviation}`)
      const section = page.getByTestId('team-board-performance')
      await expect(section).toContainText(abbreviation === 'NYY' ? '4.11' : abbreviation === 'LAD' ? '2.99' : '3.42')
      await expect(section).toContainText('1.18')
      await expect(section).toContainText('42.0 innings')
      await expect(section.getByText('Additional performance context not published')).toBeVisible()
      await expectNoPageOverflow(page)
    }
  }
})

test('TB-07 shows publication-bound recent starts across teams and widths', async ({ page }) => {
  await installApiFixtures(page)
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const abbreviation of ['BAL', 'LAD', 'NYY']) {
      await page.goto(`/bullpen?team=${abbreviation}`)
      const section = page.getByTestId('team-board-rotation-impact')
      await expect(section).toContainText(`${abbreviation} Fixture Starter`)
      await expect(section).toContainText('Starter 4.2 IP · Bullpen 4.1 IP')
      await expect(section).toContainText('Short start: fewer than 5 starter innings')
      await expect(section).toContainText('1 recent team game lacks')
      await expectNoPageOverflow(page)
    }
  }
})

test('TB-07 rejects stale details and old-team starts while preserving the answer', async ({ page }) => {
  await installApiFixtures(page, { detailsIdentityMismatch: true })
  await page.goto('/bullpen?team=BAL')
  await expect(page.getByTestId('team-board-answer-block')).toBeVisible()
  await expect(page.getByTestId('team-board-rotation-impact')).not.toContainText('BAL Fixture Starter')
  await page.getByLabel('Select team for Team Board').selectOption('119')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Los Angeles Dodgers')
  await expect(page.getByTestId('team-board-rotation-impact')).not.toContainText('BAL Fixture Starter')
})

test('TB-07 clears old-team starts during in-page team switching', async ({ page }) => {
  const fixtures = await installApiFixtures(page, { deferDetails: true })
  await page.goto('/bullpen?team=BAL')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Baltimore Orioles')
  await page.getByLabel('Select team for Team Board').selectOption('119')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Los Angeles Dodgers')
  await expect(page.getByTestId('team-board-rotation-impact')).not.toContainText('BAL Fixture Starter')
  fixtures.releaseDetails()
  await expect(page.getByTestId('rotation-recent-starts')).toContainText('LAD Fixture Starter')
  await page.getByLabel('Select team for Team Board').selectOption('147')
  await expect(page.getByTestId('rotation-recent-starts')).toContainText('NYY Fixture Starter')
  await expect(page.getByTestId('rotation-recent-starts')).not.toContainText('LAD Fixture Starter')
})

test('TB-07 fixture readiness is measured separately from core and details', async ({ page }) => {
  await installApiFixtures(page)
  const responseTimes = {}
  page.on('response', response => {
    const path = new URL(response.url()).pathname
    if (path.endsWith('/board-v2/core')) responseTimes.core = performance.now()
    if (path.endsWith('/board-v2/details')) responseTimes.details = performance.now()
  })
  const start = performance.now()
  await page.goto('/bullpen?team=BAL')
  await expect(page.getByTestId('team-board-answer-block')).toBeVisible()
  const coreReady = performance.now()
  await expect(page.getByTestId('rotation-recent-starts')).toContainText('BAL Fixture Starter')
  const rotationReady = performance.now()
  expect(responseTimes.core).toBeDefined()
  expect(responseTimes.details).toBeDefined()
  console.log(`TB-07 local fixture: core=${Math.round(coreReady - start)}ms details-response=${Math.round(responseTimes.details - start)}ms rotation-ready=${Math.round(rotationReady - start)}ms details-to-rotation=${Math.round(rotationReady - responseTimes.details)}ms`)
})

test('TB-06 stale details are withheld while core remains usable', async ({ page }) => {
  await installApiFixtures(page, { detailsIdentityMismatch: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  await expect(page.getByTestId('team-board-performance')).not.toContainText('3.42')
})

test('TB-06 drops old-team performance during deferred team switching', async ({ page }) => {
  const fixtures = await installApiFixtures(page, { deferDetails: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('performance-skeleton')).toBeVisible()
  await page.getByLabel('Select team for Team Board').selectOption('147')
  await expect(page.getByTestId('team-board-performance')).toContainText('4.11')
  fixtures.releaseDetails()
  await expect(page.getByTestId('team-board-answer-block')).toContainText('New York Yankees')
  await expect(page.getByTestId('team-board-performance')).toContainText('4.11')
  await expect(page.getByTestId('team-board-performance')).not.toContainText('3.42')
})

test('TB-06 local fixture readiness is measured separately from core and details', async ({ page }) => {
  await installApiFixtures(page)
  const responseTimes = {}
  page.on('response', response => {
    const path = new URL(response.url()).pathname
    if (path.endsWith('/board-v2/core')) responseTimes.core = performance.now()
    if (path.endsWith('/board-v2/details')) responseTimes.details = performance.now()
  })
  const start = performance.now()
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  const coreReady = performance.now()
  await expect(page.getByTestId('team-board-performance')).toContainText('3.42')
  const performanceReady = performance.now()
  expect(responseTimes.core).toBeDefined()
  expect(responseTimes.details).toBeDefined()
  console.log(`TB-06 local fixture: core=${Math.round(coreReady - start)}ms details-response=${Math.round(responseTimes.details - start)}ms performance-ready=${Math.round(performanceReady - start)}ms details-to-performance=${Math.round(performanceReady - responseTimes.details)}ms`)
})

test('TB-04 local fixture readiness is measured separately from core and details', async ({ page }) => {
  await installApiFixtures(page)
  const responseTimes = {}
  page.on('response', response => {
    const path = new URL(response.url()).pathname
    if (path.endsWith('/board-v2/core')) responseTimes.core = performance.now()
    if (path.endsWith('/board-v2/details')) responseTimes.details = performance.now()
  })
  const start = performance.now()
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByTestId('team-board-answer-block')).toContainText('Team State: Fresh')
  const coreReady = performance.now()
  await expect(page.getByTestId('team-board-workload-overview')).toContainText('Top 3 arms account for')
  const workloadReady = performance.now()
  expect(responseTimes.core).toBeDefined()
  expect(responseTimes.details).toBeDefined()
  console.log(`TB-04 local fixture: core=${Math.round(coreReady - start)}ms details-response=${Math.round(responseTimes.details - start)}ms workload-ready=${Math.round(workloadReady - start)}ms details-to-workload=${Math.round(workloadReady - responseTimes.details)}ms`)
})

test('Team Board recent usage keeps a partial carrier fail-closed', async ({ page }) => {
  await installApiFixtures(page, { partialCarrier: true })
  await page.goto('/bullpen?team=BOS')
  const recent = page.getByTestId('team-board-recent-usage')
  await expect(recent).toContainText('Recent Usage is partially available')
  await expect(recent).toContainText('Evidence incomplete: 25+ pitch outing.')
  await expect(recent).not.toContainText('pitch spike')
})

test('switching teams cannot attach a delayed carrier from the prior team', async ({ page }) => {
  const fixtures = await installApiFixtures(page, { deferDetails: true })
  await page.goto('/bullpen?team=BOS')
  await expect(page.getByText(/loading recent usage/i).first()).toBeVisible()
  await page.getByLabel('Select team for Team Board').selectOption('147')
  const recent = page.getByTestId('team-board-recent-usage')
  await expect(recent).toContainText('NYY Fixture Reliever')
  fixtures.releaseDetails()
  await expect(recent).toContainText('NYY Fixture Reliever')
  await expect(recent.getByText('Fixture Reliever', { exact: true })).toHaveCount(0)
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

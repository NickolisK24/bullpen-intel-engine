import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

const tonightPageSource = read('../src/components/tonight/TonightPage.jsx')
const leagueSource = read('../src/components/dashboard/Dashboard.jsx')
const storiesSource = read('../src/components/stories/Stories.jsx')
const trustSource = read('../src/components/trust/DataTrust.jsx')
const apiSource = read('../src/utils/api.js')
const appSource = read('../src/App.jsx')


test('each public surface uses its purpose-built projection instead of Dashboard', () => {
  const consumers = [
    [leagueSource, 'getLeagueProjection'],
    [storiesSource, 'getStoriesProjection'],
    [trustSource, 'getTrustProjection'],
  ]

  for (const [source, projection] of consumers) {
    assert.ok(source.includes(projection), projection)
    assert.equal(source.includes('getBullpenDashboard'), false, projection)
    assert.equal((source.match(new RegExp(`useFetch\\(${projection}\\)`, 'g')) || []).length, 1)
  }
})


test('purpose-built API helpers have explicit coherent routes', () => {
  // TN-11: the Home projection client was retired with the Home surface.
  assert.equal(apiSource.includes('getHomeProjection'), false)
  assert.ok(apiSource.includes("getLeagueProjection = (options = {}) => request('/bullpen/league'"))
  assert.ok(apiSource.includes("getStoriesProjection = (options = {}) => request('/bullpen/stories'"))
  assert.ok(apiSource.includes("getTrustProjection = (options = {}) => request('/bullpen/trust'"))
  assert.ok(apiSource.includes("getBullpenDashboard = () => request('/bullpen/dashboard')"))
})


test('League receives Team States inside the same projection request', () => {
  assert.ok(leagueSource.includes('league.data?.team_states'))
  assert.equal(leagueSource.includes('getLeagueTeamStates'), false)
  assert.equal((leagueSource.match(/useFetch\(/g) || []).length, 1)
})


test('the Tonight home reads only the tonight_v1 edition; legacy Home clients are retired', () => {
  assert.equal((tonightPageSource.match(/getTonightV1\(/g) || []).length, 1)
  assert.equal(tonightPageSource.includes('getBullpenLandscape'), false)
  for (const retired of ['getHomeProjection', 'getTodayIntelligence', 'getTonightIntelligence']) {
    assert.equal(tonightPageSource.includes(retired), false, retired)
    assert.equal(new RegExp(`export const ${retired}\\b`).test(apiSource), false, retired)
  }
})


test('direct public routes remain registered', () => {
  for (const route of ['/', '/dashboard', '/stories', '/trust']) {
    assert.ok(appSource.includes(`path: '${route}'`), route)
  }
})

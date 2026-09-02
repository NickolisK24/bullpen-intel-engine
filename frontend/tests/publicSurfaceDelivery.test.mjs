import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

const homeSource = read('../src/components/home/IntelligenceSurface.jsx')
const leagueSource = read('../src/components/dashboard/Dashboard.jsx')
const storiesSource = read('../src/components/stories/Stories.jsx')
const trustSource = read('../src/components/trust/DataTrust.jsx')
const apiSource = read('../src/utils/api.js')
const appSource = read('../src/App.jsx')


test('each public surface uses its purpose-built projection instead of Dashboard', () => {
  const consumers = [
    [homeSource, 'getHomeProjection'],
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
  assert.ok(apiSource.includes("getHomeProjection = () => request('/bullpen/home')"))
  assert.ok(apiSource.includes("getLeagueProjection = () => request('/bullpen/league')"))
  assert.ok(apiSource.includes("getStoriesProjection = () => request('/bullpen/stories')"))
  assert.ok(apiSource.includes("getTrustProjection = () => request('/bullpen/trust')"))
  assert.ok(apiSource.includes("getBullpenDashboard = () => request('/bullpen/dashboard')"))
})


test('League receives Team States inside the same projection request', () => {
  assert.ok(leagueSource.includes('league.data?.team_states'))
  assert.equal(leagueSource.includes('getLeagueTeamStates'), false)
  assert.equal((leagueSource.match(/useFetch\(/g) || []).length, 1)
})


test('Home keeps Today and Tonight independent of its publication projection', () => {
  assert.ok(homeSource.includes('useFetch(getTodayIntelligence)'))
  assert.ok(homeSource.includes('useFetch(getTonightIntelligence)'))
  assert.ok(homeSource.includes('useFetch(getHomeProjection)'))
  assert.equal(homeSource.includes('getBullpenLandscape'), false)
})


test('direct public routes remain registered', () => {
  for (const route of ['/', '/dashboard', '/stories', '/trust']) {
    assert.ok(appSource.includes(`path: '${route}'`), route)
  }
})

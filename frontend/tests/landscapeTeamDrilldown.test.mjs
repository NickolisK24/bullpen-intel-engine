import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const { buildLandscapeTeamHref } = await server.ssrLoadModule('/src/components/dashboard/bullpenLandscapeView.js')
const { resolveTeamId } = await server.ssrLoadModule('/src/components/bullpen/board/TonightsBullpenBoard.jsx')

// Today still consumes this legacy landscape helper. UX-2C removes only its
// retired Dashboard renderer, so the existing Today drilldown remains pinned.
test('buildLandscapeTeamHref prefers abbreviation, falls back to id, else null', () => {
  assert.equal(buildLandscapeTeamHref({ team_abbreviation: 'SF', team_id: 1 }),
    '/bullpen?view=board&team=SF&source=landscape')
  assert.equal(buildLandscapeTeamHref({ team_id: 5 }),
    '/bullpen?view=board&team=5&source=landscape')
  assert.equal(buildLandscapeTeamHref({}), null)
})

test('resolveTeamId matches abbreviation, id, and name', () => {
  const teamList = [
    { team_id: 1, team_abbreviation: 'SF', team_name: 'San Francisco' },
    { team_id: 2, team_abbreviation: 'NYY', team_name: 'New York' },
  ]
  assert.equal(resolveTeamId(teamList, 'sf'), 1)
  assert.equal(resolveTeamId(teamList, '2'), 2)
  assert.equal(resolveTeamId(teamList, 'New York'), 2)
  assert.equal(resolveTeamId(teamList, 'ZZZ'), null)
})

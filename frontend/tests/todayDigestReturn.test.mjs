import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const {
  hasDigestReturnParams,
  parseTodayTeamParam,
  relationshipFor,
  resolveTodayViewTeam,
  searchWithoutDigestReturnParams,
} = await server.ssrLoadModule('/src/utils/todayDigestReturn.js')
const {
  DigestReturnNoticeView,
  followDigestReturnTeam,
} = await server.ssrLoadModule('/src/components/home/DigestReturnNotice.jsx')
const { HomeView } = await server.ssrLoadModule('/src/components/home/Home.jsx')

const htmlIncludes = (html, text) => html.includes(text)
const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)

const royalsTeam = {
  team_id: 118,
  team_name: 'Kansas City Royals',
  team_abbreviation: 'KC',
}
const metsTeam = {
  team_id: 121,
  team_name: 'New York Mets',
  team_abbreviation: 'NYM',
}
const teams = [royalsTeam, metsTeam]

function dashboardFixture() {
  return {
    capability: 'bullpen_dashboard',
    context: {
      health: { state: 'normal', label: 'Most bullpens are in their usual lane.', reasons: [] },
      metrics: { total_relievers: 64, available: 40, monitor: 12, restricted: 8 },
    },
    freshness: { data_through: '2026-06-23', sync_status: 'success', is_current: true },
    stories: {
      capability: 'baseballos_canonical_story_v1',
      items: [],
      league_context: {
        capability: 'baseballos_league_context_v1',
        mode: 'quiet_day',
        headline: 'A quiet morning across baseball',
        summary: 'Most bullpens are in normal shape.',
        evidence: { league_team_count: 30 },
        generated: true,
        quality_status: 'published',
      },
    },
  }
}

function changesFixture(teamName = 'Kansas City Royals') {
  return {
    state: 'changes',
    comparison: {
      anchor_game_date: '2026-06-22',
      current_game_date: '2026-06-23',
      global_latest_game_date: '2026-06-23',
      label: `Compared with ${teamName}: Jun 22 -> Jun 23`,
      is_current: true,
      team_data_behind_league: false,
    },
    pitcher_changes: [
      {
        type: 'appearance',
        pitcher_id: 1,
        pitcher_name: 'Royals Relief Arm',
        game_date: '2026-06-23',
        pitches: 18,
        summary: 'Royals Relief Arm pitched Tuesday - 18 pitches.',
      },
    ],
    freshness: {
      latest_workload_date: '2026-06-23',
      is_current: true,
    },
  }
}

function renderDigestHome({
  viewTeam = royalsTeam,
  followedTeam = null,
  authenticated = false,
  changes = changesFixture(),
} = {}) {
  const teamRelationship = relationshipFor({
    urlTeamValid: true,
    authenticated,
    viewTeam,
    followedTeam,
  })

  return render(React.createElement(HomeView, {
    dashboard: dashboardFixture(),
    teams,
    preferredTeam: followedTeam,
    viewTeam,
    teamRelationship,
    authenticated,
    isDigestReturn: true,
    preferredTeamChanges: changes,
    preferredTeamPromptDismissed: true,
  }))
}

test('numeric digest team param resolves to the matching directory team and detects source', () => {
  const parsed = parseTodayTeamParam('?team=118&source=digest')
  const resolved = resolveTodayViewTeam({
    search: '?team=118&source=digest',
    teams,
    teamsLoaded: true,
    preferredTeam: metsTeam,
  })

  assert.equal(parsed.team_id, 118)
  assert.equal(parsed.isDigestReturn, true)
  assert.equal(resolved.urlTeamValid, true)
  assert.equal(resolved.viewTeam.team_name, 'Kansas City Royals')
})

test('malformed and unknown team params are invalid and fall back safely', () => {
  for (const search of ['', '?team=abc123&source=digest', '?team=-1', '?team=999999&source=digest']) {
    const resolved = resolveTodayViewTeam({
      search,
      teams,
      teamsLoaded: true,
      preferredTeam: metsTeam,
    })

    if (search) {
      assert.equal(resolved.urlTeamValid, false)
      assert.equal(resolved.viewTeam.team_name, 'New York Mets')
    } else {
      assert.equal(resolved.parsed.hasTeamParam, false)
      assert.equal(resolved.viewTeam.team_name, 'New York Mets')
    }
  }
})

test('defensive abbreviation support resolves known team abbreviations', () => {
  const resolved = resolveTodayViewTeam({
    search: '?team=KC&source=digest',
    teams,
    teamsLoaded: true,
    preferredTeam: metsTeam,
  })

  assert.equal(resolved.urlTeamValid, true)
  assert.equal(resolved.viewTeam.team_id, 118)
})

test('valid URL team beats preferred team and stays pending while teams are loading', () => {
  const pending = resolveTodayViewTeam({
    search: '?team=118&source=digest',
    teams: [],
    teamsLoaded: false,
    preferredTeam: metsTeam,
  })
  const resolved = resolveTodayViewTeam({
    search: '?team=118&source=digest',
    teams,
    teamsLoaded: true,
    preferredTeam: metsTeam,
  })

  assert.equal(pending.urlTeamPending, true)
  assert.equal(pending.viewTeam, null)
  assert.equal(resolved.viewTeam.team_name, 'Kansas City Royals')
})

test('signed-out digest return renders that team Today preview with sign-in prompt', () => {
  const html = renderDigestHome({ followedTeam: null, authenticated: false })

  assert.ok(htmlIncludes(html, 'You&#x27;re viewing the Kansas City Royals update from your digest.'))
  assert.ok(htmlIncludes(html, 'Here&#x27;s what changed for the Kansas City Royals since their last game.'))
  assert.ok(htmlIncludes(html, 'Sign in to follow this team and get future bullpen updates.'))
  assert.ok(htmlIncludes(html, 'Kansas City Royals'))
  assert.ok(htmlIncludes(html, 'href="/signin"'))
  assert.ok(htmlIncludes(html, 'Royals Relief Arm pitched Tuesday - 18 pitches.'))
  assert.ok(htmlIncludes(html, 'What Changed Since Last Game'))
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Picture'))
  assert.equal(htmlIncludes(html, 'My Team'), false)
  assert.equal(htmlIncludes(html, '>118<'), false)
})

test('signed-in digest return for followed team shows welcome-back notice without switch prompt', () => {
  const html = renderDigestHome({
    followedTeam: royalsTeam,
    authenticated: true,
  })

  assert.ok(htmlIncludes(html, 'This is already your followed team.'))
  assert.ok(htmlIncludes(html, 'Following'))
  assert.ok(htmlIncludes(html, 'Change followed team'))
  assert.ok(htmlIncludes(html, 'href="/trust?focus=digest-preferences"'))
  assert.equal(htmlIncludes(html, 'Switch followed team'), false)
  assert.equal(htmlIncludes(html, 'aria-label="Change preferred team"'), false)
})

test('signed-in digest return for another team shows URL team and switch prompt', () => {
  const html = renderDigestHome({
    followedTeam: metsTeam,
    authenticated: true,
  })

  assert.ok(htmlIncludes(html, 'Kansas City Royals'))
  assert.ok(htmlIncludes(html, 'Want to make the Kansas City Royals your followed team?'))
  assert.ok(htmlIncludes(html, 'Switch followed team'))
  assert.ok(htmlIncludes(html, 'Change followed team'))
  assert.ok(htmlIncludes(html, 'href="/trust?focus=digest-preferences"'))
  assert.equal(htmlIncludes(html, 'My Team'), false)
  assert.equal(htmlIncludes(html, 'Following'), false)
})

test('followed team is only changed after the explicit digest follow action', () => {
  let selectedTeam = null
  const html = render(React.createElement(DigestReturnNoticeView, {
    team: royalsTeam,
    relationship: relationshipFor({
      urlTeamValid: true,
      authenticated: true,
      viewTeam: royalsTeam,
      followedTeam: metsTeam,
    }),
    onFollowTeam: (team) => {
      selectedTeam = team
    },
  }))

  assert.ok(htmlIncludes(html, 'Switch followed team'))
  assert.equal(selectedTeam, null)
  assert.equal(followDigestReturnTeam(royalsTeam, (team) => {
    selectedTeam = team
  }), true)
  assert.deepEqual(selectedTeam, royalsTeam)
})

test('no params preserves followed-team Home behavior', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture(),
    teams,
    preferredTeam: metsTeam,
    viewTeam: metsTeam,
    authenticated: true,
    teamRelationship: relationshipFor({
      viewTeam: metsTeam,
      followedTeam: metsTeam,
    }),
    preferredTeamChanges: changesFixture('New York Mets'),
  }))

  assert.ok(htmlIncludes(html, 'My Team'))
  assert.ok(htmlIncludes(html, 'Following'))
  assert.ok(htmlIncludes(html, 'Change followed team'))
  assert.ok(htmlIncludes(html, 'href="/trust?focus=digest-preferences"'))
  assert.equal(htmlIncludes(html, 'aria-label="Change preferred team"'), false)
  assert.equal(htmlIncludes(html, 'Digest Update'), false)
})

test('signed-out team preview routes persistent team changes to sign-in', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardFixture(),
    teams,
    preferredTeam: null,
    viewTeam: royalsTeam,
    authenticated: false,
    teamRelationship: relationshipFor({
      viewTeam: royalsTeam,
      followedTeam: null,
    }),
    preferredTeamChanges: changesFixture('Kansas City Royals'),
    preferredTeamPromptDismissed: true,
  }))

  assert.ok(htmlIncludes(html, 'Change followed team'))
  assert.ok(htmlIncludes(html, 'href="/signin"'))
  assert.equal(htmlIncludes(html, 'aria-label="Change preferred team"'), false)
})

test('What Changed remains the first team-specific section for digest returns', () => {
  const html = renderDigestHome()

  assert.ok(html.indexOf('What Changed Since Last Game') < html.indexOf('Tonight&#x27;s Bullpen Picture'))
  assert.ok(html.indexOf('What Changed Since Last Game') < html.indexOf('What BaseballOS Sees Today'))
})

test('searchWithoutDigestReturnParams drops only the view-only digest params', () => {
  const dropped = searchWithoutDigestReturnParams('?team=118&source=digest')
  assert.equal(dropped.changed, true)
  assert.equal(dropped.params.has('team'), false)
  assert.equal(dropped.params.has('source'), false)
  assert.equal(dropped.params.toString(), '')

  // Unrelated params are preserved; team/source are still removed.
  const mixed = searchWithoutDigestReturnParams('?team=118&source=digest&keep=1')
  assert.equal(mixed.changed, true)
  assert.equal(mixed.params.get('keep'), '1')
  assert.equal(mixed.params.has('team'), false)

  // No-op when there is nothing to clear.
  const noop = searchWithoutDigestReturnParams('?keep=1')
  assert.equal(noop.changed, false)
  assert.equal(noop.params.get('keep'), '1')

  // Accepts a URLSearchParams instance and does not mutate the caller's object.
  const original = new URLSearchParams('team=118&source=digest')
  const fromInstance = searchWithoutDigestReturnParams(original)
  assert.equal(fromInstance.changed, true)
  assert.equal(fromInstance.params.has('team'), false)
  assert.equal(original.has('team'), true)

  assert.equal(hasDigestReturnParams('?team=118&source=digest'), true)
  assert.equal(hasDigestReturnParams('?keep=1'), false)
})

test('explicit team change consumes the URL override so the followed team drives Today', () => {
  // Initial digest landing: the URL team overrides the (different) followed team.
  const onLanding = resolveTodayViewTeam({
    search: '?team=118&source=digest',
    teams,
    teamsLoaded: true,
    preferredTeam: metsTeam,
  })
  assert.equal(onLanding.urlTeamValid, true)
  assert.equal(onLanding.viewTeam.team_id, 118) // Royals, from the link

  // User clicks "Switch followed team": the preference becomes Royals and the
  // override params are cleared. Today shows Royals because it is now followed,
  // not because of a stale URL override (no digest-return state remains).
  const afterSwitch = searchWithoutDigestReturnParams('?team=118&source=digest')
  const switched = resolveTodayViewTeam({
    search: afterSwitch.params.toString(),
    teams,
    teamsLoaded: true,
    preferredTeam: royalsTeam,
  })
  assert.equal(switched.urlTeamValid, false)
  assert.equal(switched.isDigestReturn, false)
  assert.equal(switched.viewTeam.team_id, 118)

  // User then changes team to the Mets via the normal selector while a stale
  // digest link is still in the URL: the override is consumed and Today follows
  // the Mets — the sidebar (preferred) and Today agree, not the old digest team.
  const afterChange = searchWithoutDigestReturnParams('?team=118&source=digest')
  const changed = resolveTodayViewTeam({
    search: afterChange.params.toString(),
    teams,
    teamsLoaded: true,
    preferredTeam: metsTeam,
  })
  assert.equal(changed.urlTeamValid, false)
  assert.equal(changed.viewTeam.team_id, 121) // New York Mets
})

test('dismissing the digest notice persists nothing and renders no notice', () => {
  let followed = null
  const html = render(React.createElement(DigestReturnNoticeView, {
    team: royalsTeam,
    relationship: relationshipFor({
      urlTeamValid: true,
      authenticated: true,
      viewTeam: royalsTeam,
      followedTeam: metsTeam,
    }),
    onFollowTeam: (team) => { followed = team },
    dismissed: true,
  }))

  assert.equal(html, '')
  assert.equal(followed, null)
})

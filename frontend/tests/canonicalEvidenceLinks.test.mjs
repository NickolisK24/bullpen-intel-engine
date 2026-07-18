import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'
import {
  buildAllPitchersHref,
  buildCanonicalBullpenHref,
  buildComparisonHref,
  buildPitcherHref,
  buildTeamBoardHref,
  normalizeBullpenSource,
  normalizeTeamReference,
  readBullpenLocation,
  resolveTeamId,
  resolveTeamReference,
} from '../src/utils/evidenceLinks.js'

const teams = [
  { team_id: 111, team_name: 'Boston Red Sox', team_abbreviation: 'BOS' },
  { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
]

const extractTagAttribute = (tag, attribute) => {
  const match = tag.match(new RegExp(`\\b${attribute}\\s*=\\s*["']([^"']*)["']`, 'i'))
  return match?.[1]?.trim() ?? ''
}

const extractHtmlTitle = html => (
  html.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.trim() ?? ''
)

const extractMetaContent = (html, selectorAttribute, selectorValue) => {
  const tag = (html.match(/<meta\b[^>]*>/gi) ?? []).find(
    candidate => extractTagAttribute(candidate, selectorAttribute) === selectorValue,
  )
  return tag ? extractTagAttribute(tag, 'content') : ''
}

const extractCanonicalHref = html => {
  const tag = (html.match(/<link\b[^>]*>/gi) ?? []).find(candidate => (
    extractTagAttribute(candidate, 'rel').split(/\s+/).includes('canonical')
  ))
  return tag ? extractTagAttribute(tag, 'href') : ''
}

test('team evidence links prefer abbreviations and use deterministic parameters', () => {
  assert.equal(
    buildTeamBoardHref(teams[0], { source: 'dashboard' }),
    '/bullpen?view=board&team=BOS&source=dashboard',
  )
  assert.equal(
    buildTeamBoardHref(teams[0], { section: 'team-relief-work' }),
    '/bullpen?view=board&team=BOS#team-relief-work',
  )
  assert.equal(
    buildTeamBoardHref(teams[0], { section: 'pitcher-lanes' }),
    '/bullpen?view=board&team=BOS#pitcher-lanes',
  )
})

test('comparison links preserve left and right order and exact evidence', () => {
  assert.equal(
    buildComparisonHref(teams[0], teams[1]),
    '/bullpen?view=compare&team_a=BOS&team_b=NYY',
  )
  assert.equal(
    buildComparisonHref(teams[1], teams[0], { section: 'comparison-evidence' }),
    '/bullpen?view=compare&team_a=NYY&team_b=BOS#comparison-evidence',
  )
})

test('pitcher links keep known team context and reject invalid ids', () => {
  assert.equal(
    buildPitcherHref(123456, { teamRef: teams[0], source: 'pitcher_search' }),
    '/bullpen?view=board&team=BOS&pitcher=123456&source=pitcher_search',
  )
  assert.equal(buildPitcherHref('12x', { teamRef: teams[0] }), '/bullpen?view=board&team=BOS')
  assert.equal(buildPitcherHref(-1, { teamRef: teams[0] }), '/bullpen?view=board&team=BOS')
})

test('invalid team, source, section, and incompatible parameters are omitted', () => {
  assert.equal(normalizeTeamReference('Boston Red Sox'), null)
  assert.equal(normalizeTeamReference('BOS&secret=1'), null)
  assert.equal(normalizeBullpenSource('unbounded'), null)
  assert.equal(
    buildTeamBoardHref('BOS&secret=1', { source: 'unbounded', section: 'comparison-evidence' }),
    '/bullpen?view=board',
  )
  assert.equal(buildAllPitchersHref({ teamRef: 'BOS', source: 'all_pitchers' }),
    '/bullpen?view=pitchers&team=BOS&source=all_pitchers')
})

test('URL parsing restores each visible bullpen state without inventing defaults', () => {
  assert.deepEqual(
    readBullpenLocation('?view=board&team=BOS&pitcher=123456&source=stories', '#pitcher-lanes'),
    {
      view: 'board', requestedView: 'board', team: 'BOS', teamA: null, teamB: null,
      pitcherId: 123456, source: 'stories', section: 'pitcher-lanes', unsupportedHash: null,
    },
  )
  const comparison = readBullpenLocation('?view=compare&team_a=BOS&team_b=NYY')
  assert.equal(buildCanonicalBullpenHref(comparison), '/bullpen?view=compare&team_a=BOS&team_b=NYY')
  const incomplete = readBullpenLocation('?view=compare&team_a=BOS')
  assert.equal(buildCanonicalBullpenHref(incomplete), '/bullpen?view=compare&team_a=BOS')
  const empty = readBullpenLocation('?view=compare')
  assert.equal(buildCanonicalBullpenHref(empty), '/bullpen?view=compare')
})

test('unknown views and incompatible parameters normalize safely', () => {
  const unknown = readBullpenLocation('?view=unknown&team=BOS&team_a=NYY&pitcher=nope&source=secret')
  assert.equal(unknown.view, 'board')
  assert.equal(buildCanonicalBullpenHref(unknown), '/bullpen?view=board&team=BOS')

  const pitchers = readBullpenLocation('?view=pitchers&team=BOS&pitcher=123&team_b=NYY')
  assert.equal(buildCanonicalBullpenHref(pitchers), '/bullpen?view=pitchers&team=BOS')
})

test('team resolution waits for the supplied list and canonicalizes supported references', () => {
  assert.equal(resolveTeamReference([], 'BOS'), null)
  assert.equal(resolveTeamId(teams, 'bos'), 111)
  assert.equal(resolveTeamId(teams, '147'), 147)
  assert.equal(resolveTeamId(teams, 'Boston Red Sox'), 111)
  assert.equal(resolveTeamId(teams, 'SEA'), null)
  assert.equal(normalizeTeamReference(resolveTeamReference(teams, '111')), 'BOS')
})

test('URL ownership is wired through navigation for team, comparison, pitcher, and all-pitcher changes', () => {
  const bullpen = readFileSync(new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url), 'utf8')
  const board = readFileSync(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const comparison = readFileSync(new URL('../src/components/bullpen/board/TeamBullpenComparison.jsx', import.meta.url), 'utf8')

  assert.ok(bullpen.includes('readBullpenLocation(location.search, location.hash)'))
  assert.ok(bullpen.includes('navigate(buildTeamBoardHref(team'))
  assert.ok(bullpen.includes('navigate(buildComparisonHref(teamA, teamB'))
  assert.ok(bullpen.includes('navigate(buildAllPitchersHref({ teamRef: team'))
  assert.ok(bullpen.includes('navigate(buildPitcherHref(pitcherId'))
  assert.ok(bullpen.includes("navigate(canonicalHref, { replace: true })"))
  assert.ok(board.includes('onClick={() => onSelectTeam(team.team_id)}'))
  assert.ok(board.includes('onSelectPitcher={onSelectPitcher}'))
  assert.equal(board.includes('appliedRequestRef'), false)
  assert.equal(comparison.includes('teamList[0].team_id'), false)
  assert.equal(comparison.includes('teamList[1].team_id'), false)
})

test('same and incomplete comparison selections never become fetch-ready', async () => {
  const source = readFileSync(
    new URL('../src/components/bullpen/board/TeamBullpenComparison.jsx', import.meta.url),
    'utf8',
  )
  assert.ok(source.includes('return teamA != null && teamB != null && teamA !== teamB'))
  assert.ok(source.includes('ready ? getTeamBullpenComparison(teamA, teamB) : Promise.resolve(null)'))
})

test('all supported evidence targets are focusable and asynchronous navigation is bounded', () => {
  const recent = readFileSync(new URL('../src/components/bullpen/TeamReliefWorkPanel.jsx', import.meta.url), 'utf8')
  const lanes = readFileSync(new URL('../src/components/bullpen/board/BullpenBoardView.jsx', import.meta.url), 'utf8')
  const comparison = readFileSync(new URL('../src/components/bullpen/board/BullpenComparisonView.jsx', import.meta.url), 'utf8')
  const hook = readFileSync(new URL('../src/hooks/useEvidenceHashNavigation.js', import.meta.url), 'utf8')

  for (const [source, id] of [
    [recent, 'team-relief-work'],
    [lanes, 'pitcher-lanes'],
    [comparison, 'comparison-evidence'],
  ]) {
    assert.ok(source.includes(`id="${id}"`))
    assert.ok(source.includes('tabIndex={-1}'))
    assert.ok(source.includes('scroll-mt-24'))
  }
  assert.ok(hook.includes('new MutationObserver'))
  assert.ok(hook.includes('MAX_MUTATION_CHECKS = 50'))
  assert.ok(hook.includes('target.focus({ preventScroll: true })'))
  assert.equal(hook.includes('setTimeout'), false)
})

test('Dashboard, Stories, Today, Compare, and preferred-team links use the canonical helper', () => {
  const files = [
    '../src/components/dashboard/bullpenLandscapeView.js',
    '../src/components/stories/storiesCanonicalFeedView.js',
    '../src/components/home/IntelligenceSurface.jsx',
    '../src/components/bullpen/board/BullpenComparisonView.jsx',
    '../src/utils/preferredTeam.js',
  ]
  for (const file of files) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8')
    assert.ok(source.includes('buildTeamBoardHref'), file)
  }
})

test('static team previews preserve all teams, synchronized Boston metadata, redirect, and generic fallback', () => {
  const teamRoot = new URL('../public/team/', import.meta.url)
  const directories = readdirSync(teamRoot, { withFileTypes: true }).filter(entry => entry.isDirectory())
  assert.equal(directories.length, 30)

  const boston = readFileSync(new URL('BOS/index.html', teamRoot), 'utf8')
  const title = extractHtmlTitle(boston)
  const description = extractMetaContent(boston, 'name', 'description')
  const ogTitle = extractMetaContent(boston, 'property', 'og:title')
  const ogDescription = extractMetaContent(boston, 'property', 'og:description')
  const twitterTitle = extractMetaContent(boston, 'name', 'twitter:title')
  const twitterDescription = extractMetaContent(boston, 'name', 'twitter:description')

  assert.notEqual(title, '')
  assert.match(title, /Boston Red Sox/)
  assert.notEqual(title, 'BaseballOS | Team Story Preview')
  assert.equal(ogTitle, title)
  assert.equal(twitterTitle, title)
  assert.notEqual(description, '')
  assert.equal(ogDescription, description)
  assert.equal(twitterDescription, description)
  assert.equal(
    extractMetaContent(boston, 'property', 'og:url'),
    'https://baseballos.app/team/BOS',
  )
  assert.equal(extractCanonicalHref(boston), 'https://baseballos.app/team/BOS')
  assert.ok(boston.includes('window.location.replace("/bullpen?view=board&team=BOS&source=share")'))

  const fallback = readFileSync(new URL('index.html', teamRoot), 'utf8')
  assert.equal(extractHtmlTitle(fallback), 'BaseballOS | Team Story Preview')
  assert.equal(
    extractMetaContent(fallback, 'property', 'og:title'),
    'BaseballOS | Team Story Preview',
  )
  assert.ok(fallback.includes('window.location.replace("/")'))
  assert.equal(fallback.includes('Boston Red Sox'), false)
})

test('canonical navigation adds no traffic or product-intelligence schema behavior', () => {
  const helper = readFileSync(new URL('../src/utils/evidenceLinks.js', import.meta.url), 'utf8')
  for (const term of ['utm_', 'traffic', 'product_intelligence', 'fetch(', 'localStorage']) {
    assert.equal(helper.includes(term), false, term)
  }
})

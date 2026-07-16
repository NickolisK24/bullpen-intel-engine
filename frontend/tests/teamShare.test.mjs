import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import {
  buildTeamSharePath,
  buildTeamShareUrl,
  normalizeTeamShareAbbreviation,
} from '../src/utils/teamShare.js'

test('team share helper builds the canonical pre-rendered team URL', () => {
  assert.equal(normalizeTeamShareAbbreviation({ team_abbreviation: ' tor ' }), 'TOR')
  assert.equal(buildTeamSharePath({ teamAbbreviation: 'sd' }), '/team/SD')
  assert.equal(
    buildTeamShareUrl({ team_abbreviation: 'TOR' }),
    'https://baseballos.app/team/TOR',
  )
  assert.equal(
    buildTeamShareUrl({ abbr: 'SD' }),
    'https://baseballos.app/team/SD',
  )
  assert.equal(existsSync(new URL('../public/team/TOR/index.html', import.meta.url)), true)
  assert.equal(existsSync(new URL('../public/team/SD/index.html', import.meta.url)), true)
})

test('stories use the bounded link-only menu without fetching card data', () => {
  const source = readFileSync('src/components/stories/Stories.jsx', 'utf8')
  const menu = readFileSync('src/components/share/EvidenceShareMenu.jsx', 'utf8')
  assert.ok(source.includes('EvidenceShareMenu'))
  assert.ok(source.includes('linkOnly'))
  assert.ok(source.includes('destinationUrl={`${EVIDENCE_CARD_ORIGIN}${story.href}`}'))
  assert.equal(menu.includes('/bullpen/teams/'), false)
  assert.equal(menu.includes('fetch('), false)
})

test('Team card fail-closed state still leaves Copy exact link available', () => {
  const menu = readFileSync('src/components/share/EvidenceShareMenu.jsx', 'utf8')
  assert.ok(menu.includes('disabled={busy || (!linkOnly && !cardAvailable)}'))
  assert.ok(menu.includes('Copy exact link'))
  assert.ok(menu.includes('disabled={busy}'))
})

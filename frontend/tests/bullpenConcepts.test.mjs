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

const conceptsModule = await server.ssrLoadModule('/src/utils/bullpenConcepts.js')
const { CONCEPT_DEFINITIONS, PITCHER_CURRENT_READ_DEFINITIONS } = conceptsModule
const { StoriesView } = await server.ssrLoadModule('/src/components/stories/Stories.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

test('every concept ships a visible name and definition', () => {
  for (const key of ['pressure', 'recovery', 'concentration']) {
    assert.ok(CONCEPT_DEFINITIONS[key].name.length > 0)
    assert.ok(CONCEPT_DEFINITIONS[key].definition.length > 20)
  }
})

// ── Surfaces ────────────────────────────────────────────────────────────────

const dashboard = {
  context: {
    health: { state: 'strained', label: 'label', reasons: [] },
    metrics: { total_relievers: 64, available: 38, monitor: 14, restricted: 9, pct_available: 59, pct_restricted: 14 },
    confidence: 'high',
  },
  landscape: {
    reference_date: '2026-06-06',
    teams_evaluated: 8,
    games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-05', as_of_count: 6, is_today: false, message: null },
    constrained_bullpens: [
      { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50 },
      { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM', total_relievers: 8, available: 3, monitor: 2, restricted: 3, pct_available: 37, pct_restricted: 37 },
    ],
    available_bullpens: [
      { team_id: 120, team_name: 'Washington Nationals', team_abbreviation: 'WSH', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12 },
    ],
    monitoring_concentration: [
      { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', total_relievers: 8, available: 4, monitor: 4, restricted: 0, pct_available: 50, pct_restricted: 0 },
    ],
    notes: [],
  },
  freshness: { data_through: '2026-06-05', last_successful_sync: '2026-06-06T08:00:00Z', is_current: true, sync_status: 'success' },
}

test('stories feed cards render unlabeled narrative instead of compact concept tags', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: {
      ...dashboard,
      stories: {
        capability: 'baseballos_canonical_story_v1',
        items: [
          {
            story_id: '141:2026-06-06', team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR',
            date: '2026-06-06', story_available: true, story_type: 'sustainability_question',
            category: 'stressed', tone: 'stress',
            headline: 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.',
            narrative: 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.\n\nThe recent workload has clustered around the same late-inning group.\n\nThe next useful read is whether support appears behind that group.',
            beats: [
              { key: 'observation', label: 'What changed', text: 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.' },
              { key: 'baseline', label: 'Comparison point', text: 'The top three arms have carried most of the recent relief work.' },
              { key: 'cause', label: 'Why it happened', text: 'That shape leaves less room behind the clean late-inning path.' },
              { key: 'constraint', label: 'What it creates', text: 'The next read is whether support appears behind that group.' },
            ],
            continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
          },
        ],
        league_context: { headline: 'League read.', summary: 'League summary.', evidence: {} },
      },
    },
  }))
  // The canonical feed card renders the narrative prose, not beat labels or
  // landscape concept tags.
  assert.ok(htmlIncludes(html, 'The next useful read is whether support appears behind that group.'))
  assert.ok(!htmlIncludes(html, 'Concentrated Workload'))
  assert.ok(!htmlIncludes(html, 'Wide Recovery Window'))
})

// ── Definition polish ───────────────────────────────────────────────────────

test('definitions stay short and plain', () => {
  for (const key of ['pressure', 'recovery', 'concentration']) {
    const { definition } = CONCEPT_DEFINITIONS[key]
    assert.ok(definition.length > 20, `${key} definition too short`)
    assert.ok(definition.length <= 80, `${key} definition should stay a single plain sentence`)
    assert.ok(definition.split('.').filter(Boolean).length === 1, `${key} definition should be one sentence`)
  }
})

test('the concept set stays at three — no new concepts were added', () => {
  assert.equal(Object.keys(CONCEPT_DEFINITIONS).length, 3)
  assert.deepEqual(
    Object.keys(CONCEPT_DEFINITIONS).sort(),
    ['concentration', 'pressure', 'recovery'],
  )
})

test('the retired team-level Clean Options is gone and stays gone', () => {
  // This file used to assert the opposite — that `cleanOptions` kept its name —
  // which pinned vocabulary the canonical standards had retired in favour of
  // `Rested Options`. The pitcher-level `Clean Option` singular is a different
  // family and is asserted intact below.
  assert.equal('cleanOptions' in CONCEPT_DEFINITIONS, false)
  assert.equal(JSON.stringify(CONCEPT_DEFINITIONS).includes('Clean Options'), false)
})

test('the named reads avoid health-tinted alternatives', () => {
  const copy = JSON.stringify(CONCEPT_DEFINITIONS).toLowerCase()
  for (const term of ['healthy', 'fit', 'injury-free', 'ready-bodied']) {
    assert.equal(copy.includes(term), false, `health-tinted term: ${term}`)
  }
})

test('the pitcher-level Clean Option read is untouched', () => {
  const names = PITCHER_CURRENT_READ_DEFINITIONS.map(entry => entry.name)
  assert.ok(names.includes('Clean Option'))
})

test('the vocabulary never reaches for prediction, betting, injury, or advice', () => {
  const { READ_CONFIDENCE_BOUNDARY, LIMITED_FAMILY_BOUNDARY,
    SUPPORTING_READ_BOUNDARY, ...catalogues } = conceptsModule
  // Boundary strings state what these reads are NOT ("not a prediction"), so
  // they are excluded here — the ban is on the vocabulary promising such a
  // thing, not on the page disclaiming it.
  const text = JSON.stringify(catalogues).toLowerCase()
  for (const term of [
    'will ', 'guarantee', 'collapse', 'injur', 'predict', 'bet ', 'betting',
    'odds', 'should use', 'recommend', 'best arm', 'best option', 'projected',
  ]) {
    assert.ok(!text.includes(term), `leaked "${term}"`)
  }
})


// ── VOC-001 / #638: the local tier engine stays deleted ─────────────────────

test('the glossary module computes no bullpen read', () => {
  // It used to derive its own pressure / recovery / concentration /
  // clean-options tiers in the browser — a second set of supporting reads
  // competing with the backend-owned ones. The module is a dictionary now.
  assert.deepEqual(Object.keys(conceptsModule).sort(), [
    'ARM_AVAILABILITY_DEFINITIONS',
    'AVAILABILITY_SCOPE_DESCRIPTION',
    'CONCEPT_DEFINITIONS',
    'CURRENT_READ_AVAILABILITY_RELATIONSHIP',
    'DATA_STATUS_DEFINITIONS',
    'DATA_THROUGH_LABEL',
    'FRESHNESS_LABEL_DEFINITIONS',
    'GENERATED_AT_LABEL',
    'LAST_CHECKED_LABEL',
    'LAST_DATA_UPDATE_LABEL',
    'LIMITED_FAMILY_BOUNDARY',
    'LIMITED_FAMILY_DISAMBIGUATION',
    'LIMITED_READ_LABEL',
    'PITCHER_CURRENT_READ_DEFINITIONS',
    'PITCHER_ROLE_DEFINITIONS',
    'PROVENANCE_LABEL_DEFINITIONS',
    'PUBLISHED_AT_LABEL',
    'READ_CONFIDENCE_BOUNDARY',
    'READ_CONFIDENCE_DEFINITIONS',
    'READ_CONFIDENCE_FAMILY',
    'RESTED_AVAILABILITY_DISTINCTION',
    'SUPPORTING_CONCEPT_DEFINITIONS',
    'SUPPORTING_READ_BOUNDARY',
    'TEAM_STATE_DEFINITIONS',
    'WORKLOAD_DATA_DEFINITIONS',
    'WORKLOAD_DATA_FAMILY',
  ])
  // Every export is a dictionary or a boundary string — none is a function.
  for (const [name, value] of Object.entries(conceptsModule)) {
    assert.notEqual(typeof value, 'function', `${name} must not be callable`)
  }
  for (const removed of ['getBullpenReads', 'getReadsForLandscapeEntry']) {
    assert.equal(removed in conceptsModule, false, `${removed} came back`)
  }
})

test('no production source imports the removed derivation functions', async () => {
  const { readdir, readFile } = await import('node:fs/promises')
  const roots = [new URL('../src/', import.meta.url)]
  const offenders = []
  while (roots.length) {
    const dir = roots.pop()
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const child = new URL(entry.name + (entry.isDirectory() ? '/' : ''), dir)
      if (entry.isDirectory()) { roots.push(child); continue }
      if (!/\.(js|jsx)$/.test(entry.name)) continue
      const source = (await readFile(child, 'utf8'))
        .split('\n')
        .filter(line => !line.trim().startsWith('//'))
        .join('\n')
      for (const removed of ['getBullpenReads', 'getReadsForLandscapeEntry']) {
        if (source.includes(removed)) offenders.push(`${entry.name}: ${removed}`)
      }
      // And no equivalent derivation quietly moved somewhere else.
      for (const helper of ['pressureRead', 'recoveryRead', 'concentrationRead', 'cleanOptionsRead']) {
        if (source.includes(`function ${helper}`)) offenders.push(`${entry.name}: ${helper}`)
      }
    }
  }
  assert.deepEqual(offenders, [])
})

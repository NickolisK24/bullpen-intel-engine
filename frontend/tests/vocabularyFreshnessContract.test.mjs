// H-11 closeout contracts.
//
// Three guards, each reasoning by semantic field rather than by demanding that
// every surface contain identical prose:
//
//   1. FRESHNESS MATRIX — each temporal field has exactly one reader label, and
//      the five clocks stay five distinct labels.
//   2. COLLISION GUARD — the specific retired/conflicting strings this package
//      removed cannot come back on a governed reader surface.
//   3. PARITY — the frontend mirrors of governed families still match the
//      catalogue they mirror, so drift fails CI instead of needing an audit.

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
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

const concepts = await server.ssrLoadModule('/src/utils/bullpenConcepts.js')
const availability = await server.ssrLoadModule('/src/components/bullpen/availabilityView.js')
const publicTeamState = await server.ssrLoadModule('/src/adapters/publicTeamState.js')

const read = path => readFile(new URL(path, import.meta.url), 'utf8')

// ── 1. Freshness matrix ────────────────────────────────────────────────────

// field -> the ONE canonical reader label for it.
const FRESHNESS_MATRIX = [
  { field: 'data_through', label: concepts.DATA_THROUGH_LABEL, meaning: 'latest completed baseball date represented' },
  { field: 'last_successful_sync', label: concepts.LAST_DATA_UPDATE_LABEL, meaning: 'last successful baseball-data write' },
  { field: 'last_checked', label: concepts.LAST_CHECKED_LABEL, meaning: 'last refresh attempt or observation' },
  { field: 'generated_at', label: concepts.GENERATED_AT_LABEL, meaning: 'artifact creation provenance' },
  { field: 'published_at', label: concepts.PUBLISHED_AT_LABEL, meaning: 'trusted publication provenance' },
]

test('every temporal field has exactly one canonical reader label', () => {
  const labels = FRESHNESS_MATRIX.map(row => row.label)
  assert.equal(new Set(labels).size, labels.length, 'two clocks share a reader label')
  for (const row of FRESHNESS_MATRIX) {
    assert.equal(typeof row.label, 'string')
    assert.ok(row.label.length > 0, `${row.field} has no label`)
  }
})

test('the glossary teaches exactly the labels the product renders', () => {
  assert.deepEqual(
    concepts.FRESHNESS_LABEL_DEFINITIONS.map(entry => entry.name),
    [concepts.DATA_THROUGH_LABEL, concepts.LAST_DATA_UPDATE_LABEL, concepts.LAST_CHECKED_LABEL],
  )
  assert.deepEqual(
    concepts.PROVENANCE_LABEL_DEFINITIONS.map(entry => entry.name),
    [concepts.GENERATED_AT_LABEL, concepts.PUBLISHED_AT_LABEL],
  )
})

// Every reader-facing surface this contract governs.
//
// The list used to sit inside one test and omitted BullpenBoardView,
// AvailabilityBadge and TeamGameContextCard — which is precisely where three
// live drifts survived #659: the Team Board rendered the retired 'Last synced:',
// the Reliever Finder badge labelled Workload Data as 'Data:', and the game
// context strip rendered a bare Read Confidence value. A surface list that a
// reader-facing component can be absent from is not a contract.
const GOVERNED_SURFACES = [
  '../src/components/home/IntelligenceSurface.jsx',
  '../src/components/Sidebar.jsx',
  '../src/components/dashboard/SyncStatus.jsx',
  '../src/components/dashboard/syncStatusView.js',
  '../src/components/dashboard/Dashboard.jsx',
  '../src/components/dashboard/bullpenLandscapeView.js',
  '../src/components/bullpen/BullpenOperatingStateCard.jsx',
  '../src/components/bullpen/AvailabilityBadge.jsx',
  '../src/components/bullpen/AvailabilitySummary.jsx',
  '../src/components/bullpen/board/TonightsBullpenBoard.jsx',
  '../src/components/bullpen/board/BullpenBoardView.jsx',
  '../src/components/bullpen/board/TeamGameContextCard.jsx',
  '../src/components/bullpen/RecentWorkPanel.jsx',
  '../src/components/bullpen/WorkloadPatterns.jsx',
  '../src/components/stories/Stories.jsx',
  '../src/components/explanations/ExplanationDisclosure.jsx',
  '../src/components/share/TeamStateArtifactCard.jsx',
  '../src/components/share/PublicShareArtifactPage.jsx',
  '../src/components/UI/Freshness.jsx',
]

// A retired label is retired in every form a JSX author can write it.
//
// The old matcher checked only `'X`, `"X` and `>X<`. `>Last synced:</span>` — the
// form the Team Board actually shipped — matched none of the three, so the
// variant sat inside the governed set and the contract stayed green. The fix is
// in the matcher, not in the production string: a label followed by a colon is
// the same label.
// Scanning source for reader strings must not read the comments that explain
// why a string is banned — otherwise documenting a ban trips it.
function withoutComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
}


function containsRetiredLabel(source, variant) {
  const escaped = variant.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  // The label must OPEN a quoted string or JSX text node and then TERMINATE —
  // optionally through a colon. Requiring termination is what keeps ordinary
  // prose out: 'Last sync failed' is a sentence about a failure, not a second
  // name for the field, and must not be flagged. Case-sensitive, because a
  // retired variant is retired in the exact casing it shipped as.
  return new RegExp(`(['"\`>])\\s*${escaped}\\s*:?\\s*(['"\`<{]|$)`, 'm').test(source)
}

test('no surface invents its own variant of a governed stamp name', async () => {
  // The retired variants, each of which named a field a second way.
  const RETIRED_STAMP_VARIANTS = [
    'Bullpen data through',
    'Published view through',
    'Baseball data through',
    'Dashboard read synced',
    'Bullpen read synced',
    'Latest data update',
    'Page checked',
    'Tonight watch generated',
    'Last synced',
    'Data Through',
    'Last Sync',
  ]
  for (const file of GOVERNED_SURFACES) {
    const source = withoutComments(await read(file))
    for (const variant of RETIRED_STAMP_VARIANTS) {
      assert.equal(
        containsRetiredLabel(source, variant),
        false,
        `${file} re-introduces the retired stamp variant "${variant}"`,
      )
    }
  }
})

// ── 2. Collision guard ─────────────────────────────────────────────────────

test('internal readiness wording cannot reach a share surface', async () => {
  const SHARE_SURFACES = [
    '../src/utils/shareCardArtifact.js',
    '../src/utils/evidenceCardRenderer.js',
    '../src/components/share/TeamStateArtifactCard.jsx',
    '../src/components/share/PublicShareArtifactPage.jsx',
  ]
  for (const file of SHARE_SURFACES) {
    const source = await read(file)
    for (const internal of ['Operationally Stable', 'Operationally Constrained', 'Operationally Stressed']) {
      assert.equal(source.includes(internal), false, `${file} carries ${internal}`)
    }
  }
})

test('the share card only accepts a canonical public Team State', async () => {
  const mod = await server.ssrLoadModule('/src/utils/shareCardArtifact.js')
  const projection = headline => ({
    available: true,
    card: {
      source: 'immutable_share_artifact',
      team: { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' },
      headline,
      summary: 'A summary.',
      receipts: [],
      product_date: '2026-08-13',
      trust: {},
    },
  })
  for (const label of publicTeamState.PUBLIC_TEAM_STATE_LABELS) {
    assert.ok(mod.buildTeamShareCardFromArtifact(projection(label)), label)
  }
  for (const bad of ['Operationally Stressed', 'operationally_stressed', 'Healthy', 'Unknown', null]) {
    assert.equal(mod.buildTeamShareCardFromArtifact(projection(bad)), null, String(bad))
  }
})

test('the retired Read Confidence alias is gone from labels, tooltips, and ARIA', async () => {
  const SURFACES = [
    '../src/components/bullpen/board/BullpenBoardView.jsx',
    '../src/components/dashboard/availabilityDashboardSummaryView.js',
    '../src/components/bullpen/AvailabilitySummary.jsx',
    '../src/components/share/TeamStateArtifactCard.jsx',
    '../src/components/share/PublicShareArtifactPage.jsx',
  ]
  for (const file of SURFACES) {
    const source = await read(file)
    // 'Workload Read'/'workload read' as a FIELD NAME for this family.
    assert.equal(/workload read(?: mix)?['"`:,]/i.test(source), false, `${file} still names the field "workload read"`)
    // A bare "Confidence" field label, which lets a lone "High" read as a verdict.
    assert.equal(/>Confidence<|'Confidence'|"Confidence"/.test(source), false, `${file} renders a bare Confidence label`)
  }
})

test('the pitcher workload-record family is not called Data Status', async () => {
  const source = await read('../src/components/bullpen/AvailabilitySummary.jsx')
  assert.ok(source.includes('WORKLOAD_DATA_FIELD_LABEL'))
  assert.equal(source.includes("'Data Status'"), false)
  assert.equal(source.includes('>Data Status<'), false)
  // 'Fresh' is a Team State label and must not be a workload-record value.
  assert.equal(availability.WORKLOAD_DATA_LABELS.includes('Fresh'), false)
})

test('Data Status and Workload Data stay separate families', () => {
  const dataStatus = concepts.DATA_STATUS_DEFINITIONS.map(entry => entry.name)
  const workloadData = concepts.WORKLOAD_DATA_DEFINITIONS.map(entry => entry.name)
  assert.deepEqual(dataStatus, ['Current', 'Partial Data', 'Stale', 'Data Unavailable'])
  assert.notEqual(concepts.WORKLOAD_DATA_FAMILY, 'Data Status')
  // They may share an ordinary word like 'Current' (same meaning, different
  // subject named by the field label); they may not be the same value set.
  assert.notDeepEqual(dataStatus, workloadData)
  for (const teamState of concepts.TEAM_STATE_DEFINITIONS.map(entry => entry.name)) {
    assert.equal(dataStatus.includes(teamState), false, `Data Status borrows the baseball word ${teamState}`)
    assert.equal(workloadData.includes(teamState), false, `Workload Data borrows the baseball word ${teamState}`)
  }
})

test('Today no longer title-cases backend enums into reader copy', async () => {
  const source = await read('../src/components/home/IntelligenceSurface.jsx')
  assert.equal(source.includes('function displayKey'), false)
  assert.equal(/\bdisplayKey\(/.test(source), false)
})

// ── 3. Parity and fail-closed behaviour ────────────────────────────────────

test('Read Confidence has one field-label owner, used by the glossary too', () => {
  assert.equal(availability.READ_CONFIDENCE_FIELD_LABEL, 'Read Confidence')
  assert.equal(concepts.READ_CONFIDENCE_FAMILY, availability.READ_CONFIDENCE_FIELD_LABEL)
  assert.deepEqual(
    concepts.READ_CONFIDENCE_DEFINITIONS.map(entry => entry.name),
    ['High', 'Medium', 'Low', 'Unavailable'],
  )
})

test('the Team State mirror matches its code/label pairing', () => {
  assert.deepEqual([...publicTeamState.PUBLIC_TEAM_STATE_CODES], ['fresh', 'stretched', 'vulnerable'])
  assert.deepEqual([...publicTeamState.PUBLIC_TEAM_STATE_LABELS], ['Fresh', 'Stretched', 'Vulnerable'])
  assert.deepEqual(
    concepts.TEAM_STATE_DEFINITIONS.map(entry => entry.name),
    [...publicTeamState.PUBLIC_TEAM_STATE_LABELS],
  )
})

test('the availability glossary matches the rendered availability labels', () => {
  const rendered = ['Available', 'Monitor', 'Limited', 'Unavailable']
    .map(status => availability.getAvailabilityStatusLabel(status))
  assert.deepEqual(rendered, ['Available', 'On Watch', 'Limited', 'Unavailable'])
  assert.deepEqual(
    concepts.ARM_AVAILABILITY_DEFINITIONS.map(entry => entry.name),
    ['Available', 'On Watch', 'Limited', 'Unavailable'],
  )
  // The internal engine words never reach a reader as labels.
  assert.equal(rendered.includes('Monitor'), false)
  assert.equal(rendered.includes('Avoid'), false)
  assert.equal(availability.getAvailabilityStatusLabel('Avoid'), 'Unavailable')
})

test('unknown governed values fail closed instead of being prettified', () => {
  // Availability: an unknown token yields no label rather than being echoed.
  assert.equal(availability.getAvailabilityStatusLabel('some_internal_enum'), '')
  assert.equal(availability.getAvailabilityStatusLabel('deterministic_sample_state'), '')

  // Read Confidence: an unknown token resolves to the governed absent value.
  assert.equal(availability.formatConfidence('some_internal_enum'), 'Unavailable')
  assert.equal(availability.formatConfidence(''), 'Unavailable')
  assert.equal(availability.formatConfidence(null), 'Unavailable')

  // Workload Data: an unknown state resolves to the governed entry, and is
  // flagged so a caller can omit the row without reading display text.
  const unknown = availability.getDataStateView('some_internal_enum')
  assert.equal(unknown.isKnown, false)
  assert.equal(unknown.isCurrent, false)
  assert.ok(availability.WORKLOAD_DATA_LABELS.includes(unknown.label))
  assert.equal(/Some Internal Enum/i.test(unknown.label), false)

  // A known state carries its key, so styling never depends on the label text.
  const fresh = availability.getDataStateView('fresh')
  assert.equal(fresh.isCurrent, true)
  assert.equal(fresh.label, 'Current')
})

// ── The exact drifts #659 missed, pinned by name ────────────────────────────

test('the retired-label matcher catches a trailing-colon JSX form', () => {
  // The regression that let 'Last synced:' survive: the old matcher checked
  // only `'X`, `"X` and `>X<`, and the shipped form was `>Last synced:</span>`.
  assert.equal(containsRetiredLabel('<span>Last synced:</span>', 'Last synced'), true)
  assert.equal(containsRetiredLabel("label: 'Last synced'", 'Last synced'), true)
  assert.equal(containsRetiredLabel('<span>Last synced</span>', 'Last synced'), true)

  // ...without flagging ordinary prose that merely starts with the same words.
  assert.equal(containsRetiredLabel("syncLabel: 'Last sync failed'", 'Last Sync'), false)
})

test('no governed surface labels a semantic field with an invented name', async () => {
  // Scoped to the specific inventions the integrity audit found reachable.
  // These are field-label forms, not a ban on the English words.
  const INVENTED_FIELD_LABELS = [
    'Data:',            // Workload Data rendered under an invented short name
    'Data State',       // the same family under a second invented name
  ]
  for (const file of GOVERNED_SURFACES) {
    const source = withoutComments(await read(file))
    for (const invented of INVENTED_FIELD_LABELS) {
      assert.equal(
        source.includes(`>${invented}`) || source.includes(`'${invented}`) || source.includes(`"${invented}`),
        false,
        `${file} labels a semantic field "${invented}"`,
      )
    }
  }
})

test('Data Status never borrows a value from another family', async () => {
  // 'Limited' is arm-availability vocabulary and 'Checking' was never governed.
  // Both shipped under the Data Status field label on /trust.
  const source = withoutComments(await read('../src/components/dashboard/SyncStatus.jsx'))

  assert.equal(source.includes('status="Limited"'), false)
  assert.equal(source.includes('status="Checking"'), false)
  assert.ok(source.includes('DATA_STATUS_LABELS'))
})

test('normal Read Confidence stays quiet in game context', async () => {
  // Rendered, not grepped: a string count cannot tell whether the value that
  // reached the reader carried its field name. Both components below shipped a
  // bare value — one in a metadata strip, one as a parenthetical after a role.
  const { READ_CONFIDENCE_FIELD_LABEL } = await server.ssrLoadModule(
    '/src/components/bullpen/availabilityView.js',
  )
  const TeamGameContextCard = (await server.ssrLoadModule(
    '/src/components/bullpen/board/TeamGameContextCard.jsx',
  )).default

  const html = renderToStaticMarkup(
    React.createElement(TeamGameContextCard, {
      gameContext: {
        available: true,
        state: 'stored_game_log',
        data_state: 'current',
        opponent: 'San Francisco Giants',
        opponent_abbreviation: 'SF',
        game_date: '2026-08-13',
        confidence: 'high',
        is_today: false,
        team: { team_name: 'Arizona Diamondbacks', team_abbreviation: 'AZ' },
      },
    }),
  )

  assert.equal(html.includes('High'), false)
  assert.equal(html.includes(READ_CONFIDENCE_FIELD_LABEL), false)
})

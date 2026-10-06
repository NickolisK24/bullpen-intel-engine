import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { frozenPublicDeploymentFixture, governedRoleMovementFixture } from './fixtures/teamBoardFrozenDeployment.mjs'
import { readTeamBoardFrozenDeployment } from '../src/adapters/teamBoardV2.js'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const { default: TeamBoardRolesDeployment, getRoleCompositionRows, getDeploymentRows } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRolesDeployment.jsx',
)

const rolesDeployment = {
  population_basis: 'current_visible_active_bullpen_public_role_reads',
  arm_count: 5,
  role_arm_count: 4,
  missing_role_count: 1,
  roles: [
    { role_key: 'coverage_arm', label: 'Coverage Arm', arm_count: 2 },
    { role_key: 'trust_arm', label: 'Trusted Arm', arm_count: 1 },
    { role_key: 'limited_read', label: 'Role Unclear', arm_count: 1 },
  ],
  deployment_profile: {
    status: 'complete',
    summary: 'Two arms recorded a save or hold and one arm worked multiple innings.',
    profiles: [{
      pitcher_id: 41,
      pitcher_name: 'Example Pitcher',
      summary: 'Example Pitcher recorded 0 saves, 2 holds, and worked multiple innings in 1 of 4 relief appearances with recorded outs during the 14-day window.',
    }],
  },
}

const read = {
  rolesDeployment,
  sectionStatus: {
    roles_deployment: { status: 'partial', limitations: ['Some current arms do not have a public role read.'] },
  },
}

const renderRoles = props => renderToStaticMarkup(React.createElement(TeamBoardRolesDeployment, props))
const publicationIdentity = { team_id: 111, represented_date: '2026-09-02', publication_authority_contract: 'trusted_dashboard_publication_v1' }
const frozen = () => readTeamBoardFrozenDeployment(frozenPublicDeploymentFixture(), publicationIdentity)

test('Roles & Deployment preserves backend role order, labels, and counts', () => {
  const rows = getRoleCompositionRows(rolesDeployment)
  const html = renderRoles({ read })

  assert.deepEqual(rows.map(row => row.label), [
    'Coverage Arm', 'Trusted Arm', 'Role Unclear', 'Role unavailable',
  ])
  assert.ok(html.indexOf('Coverage Arm') < html.indexOf('Trusted Arm'))
  assert.ok(html.includes('2 arms'))
  assert.ok(html.includes('1 arm'))
  assert.ok(html.includes('Some current arms do not have a public role read.'))
})

test('missing role stays neutral and is not rewritten as a governed role', () => {
  const html = renderRoles({ read: {
    rolesDeployment: {
      ...rolesDeployment,
      arm_count: 1,
      role_arm_count: 0,
      roles: [],
      missing_role_count: 1,
    },
    sectionStatus: read.sectionStatus,
  } })

  assert.ok(html.includes('Role unavailable'))
  assert.equal(html.includes('Trusted Arm'), false)
  assert.equal(html.includes('Role Unclear'), false)
})

test('observed deployment renders backend-authored prose verbatim without role inference', () => {
  const html = renderRoles({ read })
  const deploymentRows = getDeploymentRows(rolesDeployment)

  assert.deepEqual(deploymentRows, [{
    key: 'pitcher-41',
    name: 'Example Pitcher',
    summary: rolesDeployment.deployment_profile.profiles[0].summary,
  }])
  assert.ok(html.includes(rolesDeployment.deployment_profile.summary))
  assert.ok(html.includes(rolesDeployment.deployment_profile.profiles[0].summary))
  for (const forbidden of ['leverage', 'closer hierarchy', 'manager', 'preferred', 'role movement']) {
    assert.equal(html.toLowerCase().includes(forbidden.toLowerCase()), false, forbidden)
  }
})

test('role labels stay neutral and role composition is never rebuilt in the browser', async () => {
  const html = renderRoles({ read })
  const componentSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardRolesDeployment.jsx', import.meta.url), 'utf8')

  for (const label of ['Coverage Arm', 'Trusted Arm', 'Role Unclear']) {
    assert.ok(html.includes(label))
  }
  for (const forbiddenClass of ['state-clear', 'state-caution', 'state-constrained', 'rounded-full', 'role-marker']) {
    assert.equal(componentSource.includes(forbiddenClass), false, forbiddenClass)
  }
  for (const forbiddenCalculation of ['.reduce(', 'Math.', 'leverage_share', 'role_movement']) {
    assert.equal(componentSource.includes(forbiddenCalculation), false, forbiddenCalculation)
  }
})

test('Roles & Deployment distinguishes loading, unavailable, error, and empty states', () => {
  assert.ok(renderRoles({ loading: true }).includes('roles-deployment-skeleton'))
  assert.ok(renderRoles({ read: null }).includes('backend-authored role composition'))
  assert.ok(renderRoles({ read: {
    rolesDeployment,
    sectionStatus: { roles_deployment: { status: 'unavailable' } },
  } }).includes('Current role composition is unavailable.'))
  const errorHtml = renderRoles({ read, error: 'private exception' })
  assert.ok(errorHtml.includes('Current role composition could not be loaded.'))
  assert.equal(errorHtml.includes('private exception'), false)
  assert.ok(renderRoles({ read: {
    rolesDeployment: { ...rolesDeployment, arm_count: 0, role_arm_count: 0, missing_role_count: 0, roles: [] },
    sectionStatus: { roles_deployment: { status: 'available' } },
  } }).includes('No current role reads'))
})

test('production uses the shared v2 request and leaves later packages untouched', async () => {
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const componentSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardRolesDeployment.jsx', import.meta.url), 'utf8')

  assert.equal((boardSource.match(/getTeamBoardCore\(/g) || []).length, 1)
  assert.ok(boardSource.includes('<TeamBoardRolesDeployment'))
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  assert.ok(boardSource.indexOf('<TeamBoardWorkloadOverview') < boardSource.indexOf('<TeamBoardRolesDeployment'))
  assert.ok(boardSource.includes('<TeamBoardPerformance'))
  assert.ok(boardSource.includes('<SectionPair label="Roles and performance" ratio="7:5">'))
  assert.ok(boardSource.includes('<TeamBoardRotationImpact'))
  for (const forbidden of ['.sort(', '.reduce(', 'Math.', 'role_movement']) {
    assert.equal(componentSource.includes(forbidden), false, forbidden)
  }
})

test('frozen named-arm deployment renders backend role, entry, score, recorded leverage, and factual usage', () => {
  const html = renderRoles({ read: { ...read, frozenPublicDeployment: frozen() } })
  for (const expected of ['Trusted Arm', 'Role confidence: high', 'Inning 7: 1', 'Inning 9: 2',
    '3 entered 8th or later', '2 leading · 1 tied · 1 trailing', '2 high · 1 middle · 1 low',
    '2 saves', '1 hold', '2 games finished', '1 multi-inning appearance',
    'appearance-level index, not necessarily leverage at entry']) assert.ok(html.includes(expected), expected)
  for (const forbidden of ['Closer', 'moving up', 'manager', 'tonight', 'next save']) assert.equal(html.includes(forbidden), false)
})

test('entry, score, and leverage limitations are independent and missing leverage is never low', () => {
  const carrier = frozenPublicDeploymentFixture()
  const context = carrier.profiles[0].context
  context.entry_inning = { ...context.entry_inning, status: 'partial', known_appearances: 3, by_inning: [{ inning: 8, appearances: 1 }, { inning: 9, appearances: 2 }], eighth_or_later_appearances: 3 }
  context.score_context = { ...context.score_context, status: 'unknown', known_appearances: 0, leading: 0, tied: 0, trailing: 0 }
  context.leverage = { ...context.leverage, status: 'unknown', known_appearances: 0, high: 0, middle: 0, low: 0 }
  const html = renderRoles({ read: { ...read, frozenPublicDeployment: readTeamBoardFrozenDeployment(carrier, publicationIdentity) } })
  assert.ok(html.includes('partial, 3 of 4 known'))
  assert.ok(html.includes('Inning 9: 2'))
  assert.ok(html.includes('Score at entry'))
  assert.ok(html.includes('Recorded leverage'))
  assert.equal(html.includes('0 high · 0 middle · 0 low'), false)
  assert.ok(html.includes('unknown'))
  assert.ok(html.includes('2 saves'))
})

test('deployment defaults to compact summaries and preserves full evidence in native disclosures', () => {
  const deployment = frozen()
  deployment.profiles.push({
    ...structuredClone(deployment.profiles[0]),
    pitcherId: 202,
    name: 'Second Reliever',
  })
  deployment.profiles.forEach(profile => {
    profile.leverage = { ...profile.leverage, status: 'unknown', low: null, middle: null, high: null }
  })
  const html = renderRoles({ read: {
    ...read,
    frozenPublicDeployment: deployment,
  } })

  assert.equal((html.match(/<details/g) || []).length, 2)
  assert.equal((html.match(/View deployment detail/g) || []).length, 2)
  assert.equal((html.match(/Recorded leverage is not published/g) || []).length, 1)
  assert.equal(html.includes('Recorded leverage</dt>'), false)
  assert.ok(html.includes('Inning 9: 2'))
})

test('all five public role labels render verbatim and extras remain exact counts', () => {
  const labels = ['Trusted Arm', 'Setup Arm', 'Coverage Arm', 'Middle Relief Arm', 'Role Unclear']
  for (const label of labels) {
    const carrier = frozenPublicDeploymentFixture()
    carrier.profiles[0].public_role_read.label = label
    carrier.profiles[0].context.entry_inning.by_inning = [{ inning: 10, appearances: 1 }]
    carrier.profiles[0].context.entry_inning.extra_inning_appearances = 1
    const html = renderRoles({ read: { ...read, frozenPublicDeployment: readTeamBoardFrozenDeployment(carrier, publicationIdentity) } })
    assert.ok(html.includes(label), label)
    assert.ok(html.includes('Inning 10: 1'))
    assert.ok(html.includes('1 extra-inning entry'))
  }
})

test('invalid frozen identity withholds TB-05 even when a legacy prose profile exists', () => {
  const html = renderRoles({ read: { ...read, frozenPublicDeployment: null, frozenPublicDeploymentRejected: true } })
  assert.ok(html.includes('Deployment identity does not match this Team Board'))
  assert.equal(html.includes('Example Pitcher recorded'), false)
})

test('frontend does not calculate role, leverage bands, movement, or future deployment', async () => {
  const componentSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardRolesDeployment.jsx', import.meta.url), 'utf8')
  const adapterSource = await readFile(new URL('../src/adapters/teamBoardV2.js', import.meta.url), 'utf8')
  for (const source of [componentSource, adapterSource]) {
    for (const forbidden of ['1.5', '0.85', 'next save', 'Closer']) assert.equal(source.includes(forbidden), false, forbidden)
  }
  // The adapter reads the frozen carrier key; the component never sees it.
  assert.equal(componentSource.includes('role_movement'), false)
  for (const forbidden of ['.reduce(', 'Math.', 'save ?']) assert.equal(componentSource.includes(forbidden), false, forbidden)
  // No movement threshold, minimum, or direction rule exists in the browser.
  const movementSource = adapterSource.slice(adapterSource.indexOf('const ROLE_MOVEMENT_CONTRACT'), adapterSource.indexOf('export function readTeamBoardFrozenDeployment'))
  for (const forbidden of ['MIN_APPEARANCES', '>= 3', '< 3', '0.5', ' / ', 'Math.', 'shifted toward']) {
    assert.equal(movementSource.includes(forbidden), false, forbidden)
  }
  // Counts are only checked against each other for consistency, never against a threshold.
  assert.equal(/appearances\s*[<>]=?\s*\d/.test(movementSource), false)
})

const withMovement = movement => {
  const carrier = frozenPublicDeploymentFixture()
  carrier.role_movement = movement
  return carrier
}
const readCarrier = carrier => readTeamBoardFrozenDeployment(carrier, publicationIdentity)
const renderCarrier = carrier => renderRoles({ read: { ...read, frozenPublicDeployment: readCarrier(carrier) } })

test('governed role movement renders the backend sentence and factual window counts', () => {
  const html = renderCarrier(withMovement(governedRoleMovementFixture()))
  assert.ok(html.includes('role-movement-note'))
  assert.ok(html.includes('Recent deployment shifted toward later-inning, higher-leverage work.'))
  assert.ok(html.includes('Recent 7 days: 3 appearances'))
  assert.ok(html.includes('Prior 7 days: 3 appearances'))
  for (const forbidden of ['Closer', 'promot', 'demot', 'manager', 'trust him', 'next save', 'depth chart', 'will ']) {
    assert.equal(html.toLowerCase().includes(forbidden.toLowerCase()), false, forbidden)
  }
})

test('earlier or lower movement renders exactly the backend-authored copy', () => {
  const html = renderCarrier(withMovement(governedRoleMovementFixture({
    movement: 'earlier_or_lower_leverage',
    publicLabel: 'Recent deployment shifted toward earlier-inning work.',
  })))
  assert.ok(html.includes('Recent deployment shifted toward earlier-inning work.'))
})

test('the frontend never derives direction from counts or re-applies evidence minimums', () => {
  // The frozen counts would not support a shift on their own; the browser does
  // not second-guess the backend, it renders the published judgement verbatim.
  const movement = governedRoleMovementFixture({ recentAppearances: 1, priorAppearances: 1 })
  const html = renderCarrier(withMovement(movement))
  assert.ok(html.includes('Recent deployment shifted toward later-inning, higher-leverage work.'))
  assert.ok(html.includes('Recent 7 days: 1 appearance'))
})

test('stable, withheld, and partial-team movement stay locally quiet', () => {
  const stable = governedRoleMovementFixture({ movement: 'stable', publicLabel: null })
  const withheld = governedRoleMovementFixture({
    status: 'unavailable', movement: null, publicLabel: null,
    reasonCode: 'season_phase_boundary', recentAppearances: 0, priorAppearances: 0,
  })
  for (const movement of [stable, withheld]) {
    const carrier = withMovement(movement)
    const deployment = readCarrier(carrier)
    assert.ok(deployment.roleMovement, 'valid carrier reads')
    const html = renderCarrier(carrier)
    assert.equal(html.includes('role-movement-note'), false)
    assert.equal(html.includes('shifted'), false)
    assert.ok(html.includes('Trusted Arm'))
  }
})

test('old immutable publications without governed movement stay readable and quiet', () => {
  for (const legacy of [undefined, null, { status: 'unavailable', reason_code: 'not_published' }]) {
    const carrier = frozenPublicDeploymentFixture()
    if (legacy === undefined) delete carrier.role_movement
    else carrier.role_movement = legacy
    const deployment = readCarrier(carrier)
    assert.ok(deployment, 'deployment still reads')
    assert.equal(deployment.roleMovement, null)
    const html = renderCarrier(carrier)
    assert.equal(html.includes('role-movement-note'), false)
    assert.ok(html.includes('Inning 9: 2'))
  }
})

test('malformed or mismatched movement withholds movement only, never the deployment', () => {
  const cases = [
    movement => { movement.contract = 'observed_role_movement_v2' },
    movement => { movement.data_through = '2026-09-01' },
    movement => { movement.game_types = ['R'] },
    movement => { movement.profiles[0].recent_window.through_date = '2026-09-01' },
    movement => { movement.profiles[0].public_label = '' },
    movement => { movement.profiles[0].movement = 'promoted_to_closer' },
    movement => { movement.profiles[0].reason_code = 'x' },
    movement => { movement.profiles[0].recent_window.known_entry_appearances = 9 },
    movement => { movement.profiles[0].recent_window.season_phase = 'spring' },
    movement => { Object.assign(movement.profiles[0], { status: 'unavailable', reason_code: 'x' }) },
    movement => { Object.assign(movement.profiles[0], { movement: 'stable' }) },
    movement => { movement.profiles.push(structuredClone(movement.profiles[0])) },
    movement => { movement.profiles = null },
  ]
  for (const mutate of cases) {
    const movement = governedRoleMovementFixture()
    mutate(movement)
    const carrier = withMovement(movement)
    const deployment = readCarrier(carrier)
    assert.ok(deployment, mutate.toString())
    assert.equal(deployment.roleMovement, null, mutate.toString())
    assert.equal(renderCarrier(carrier).includes('role-movement-note'), false)
  }
})

test('movement for a pitcher outside the rendered deployment never renders', () => {
  const html = renderCarrier(withMovement(governedRoleMovementFixture({ pitcherId: 999 })))
  assert.equal(html.includes('role-movement-note'), false)
})

test('movement inherits the deployment carrier frozen identity', () => {
  const carrier = withMovement(governedRoleMovementFixture())
  assert.equal(readTeamBoardFrozenDeployment(carrier, { ...publicationIdentity, team_id: 112 }), null)
  assert.equal(readTeamBoardFrozenDeployment(carrier, { ...publicationIdentity, represented_date: '2026-09-03' }), null)
})

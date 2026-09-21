import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { frozenPublicDeploymentFixture } from './fixtures/teamBoardFrozenDeployment.mjs'
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
  for (const forbidden of ['.sort(', '.reduce(', 'Math.', 'roleMovement', 'role_movement']) {
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
    for (const forbidden of ['1.5', '0.85', 'role_movement', 'next save', 'Closer']) assert.equal(source.includes(forbidden), false, forbidden)
  }
  for (const forbidden of ['.reduce(', 'Math.', 'save ?']) assert.equal(componentSource.includes(forbidden), false, forbidden)
})

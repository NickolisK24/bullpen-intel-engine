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

after(async () => server.close())

const { default: TeamBoardRolesDeployment, getRoleCompositionRows } = await server.ssrLoadModule(
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
}

const read = {
  rolesDeployment,
  sectionStatus: {
    roles_deployment: { status: 'partial', limitations: ['Some current arms do not have a public role read.'] },
  },
}

const renderRoles = props => renderToStaticMarkup(React.createElement(TeamBoardRolesDeployment, props))

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

test('role composition remains team-level and exposes no unsupported deployment intelligence', () => {
  const html = renderRoles({ read })

  for (const forbidden of [
    'leverage', 'closer hierarchy', 'manager', 'preferred', 'role movement',
    'save', 'hold', 'inning entered', 'multi-inning',
  ]) {
    assert.equal(html.toLowerCase().includes(forbidden.toLowerCase()), false, forbidden)
  }
  assert.equal(html.includes('Example Pitcher'), false)
  assert.ok(html.includes('Deployment detail unavailable'))
  assert.ok(html.includes('Detailed team deployment context is not published for Team Board.'))
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
  for (const forbiddenCalculation of ['.reduce(', 'saves', 'holds', 'leverage_share', 'multi_inning', 'role_movement']) {
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

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(boardSource.includes('<TeamBoardRolesDeployment'))
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  assert.ok(boardSource.indexOf('<TeamBoardWorkloadOverview') < boardSource.indexOf('<TeamBoardRolesDeployment'))
  assert.ok(boardSource.includes('<TeamBoardPerformance'))
  assert.ok(boardSource.includes('<SectionPair label="Roles and performance" ratio="7:5">'))
  assert.ok(boardSource.includes('<TeamBoardRotationImpact'))
  for (const forbidden of ['.sort(', '.reduce(', 'Math.', 'leverage', 'roleMovement', 'role_movement']) {
    assert.equal(componentSource.includes(forbidden), false, forbidden)
  }
})

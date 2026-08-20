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

const { default: SectionPair } = await server.ssrLoadModule('/src/components/UI/SectionPair.jsx')

test('section pair stays stacked below 1024 and preserves two columns at 1024', () => {
  const html = renderToStaticMarkup(React.createElement(
    SectionPair,
    { label: 'Rest and workload' },
    React.createElement('section', null, 'Available'),
    React.createElement('section', null, 'Unavailable'),
  ))

  assert.ok(html.includes('gap-section'))
  assert.ok(html.includes('lg:grid-cols-2'))
  assert.ok(html.includes('lg:gap-8'))
  assert.ok(html.includes('[&amp;&gt;*]:min-w-0'))
  assert.equal(html.includes('tablet:grid-cols-2'), false)
  assert.ok(html.includes('Available'))
  assert.ok(html.includes('Unavailable'))
  assert.ok(html.includes('data-ratio="1:1"'))
})

test('section pair reuses the same primitive for the approved 7:5 desktop ratio', () => {
  const html = renderToStaticMarkup(React.createElement(
    SectionPair,
    { label: 'Roles and performance', ratio: '7:5' },
    React.createElement('section', null, 'Roles'),
    React.createElement('section', null, 'Performance unavailable'),
  ))

  assert.ok(html.includes('lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]'))
  assert.ok(html.includes('data-ratio="7:5"'))
  assert.equal(html.includes('lg:grid-cols-2'), false)
  assert.ok(html.includes('Performance unavailable'))
})

test('Rotation and Transactions reuse the default 1:1 pair at 1024', () => {
  const html = renderToStaticMarkup(React.createElement(
    SectionPair,
    { label: 'Rotation and transactions' },
    React.createElement('section', null, 'Rotation'),
    React.createElement('section', null, 'Transactions unavailable'),
  ))

  assert.ok(html.includes('lg:grid-cols-2'))
  assert.ok(html.includes('data-ratio="1:1"'))
  assert.ok(html.includes('Transactions unavailable'))
})

test('Rest and Workload are the only first-pair members and later sections remain outside it', async () => {
  const source = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const pairStart = source.indexOf('<SectionPair label="Rest and workload">')
  const pairEnd = source.indexOf('</SectionPair>', pairStart)

  assert.ok(pairStart >= 0)
  assert.ok(source.indexOf('<TeamBoardRestStatus', pairStart) < pairEnd)
  assert.ok(source.indexOf('<TeamBoardWorkloadOverview', pairStart) < pairEnd)
  assert.ok(source.indexOf('<TeamBoardRolesDeployment') > pairEnd)
  assert.equal((source.match(/<SectionPair/g) || []).length, 3)
  const thirdPairStart = source.indexOf('<SectionPair label="Rotation and transactions">')
  const thirdPairEnd = source.indexOf('</SectionPair>', thirdPairStart)
  assert.ok(source.indexOf('<TeamBoardRotationImpact', thirdPairStart) < thirdPairEnd)
  assert.ok(source.indexOf('<TeamBoardRecentTransactions', thirdPairStart) < thirdPairEnd)
})

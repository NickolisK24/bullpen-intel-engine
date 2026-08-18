import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import tailwindConfig from '../tailwind.config.js'
import { designTokens } from '../src/styles/designTokens.js'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: ActiveArmRow, ActiveArmRowSkeleton } =
  await server.ssrLoadModule('/src/components/bullpen/board/ActiveArmRow.jsx')
const { default: SemanticLabel } =
  await server.ssrLoadModule('/src/components/UI/SemanticLabel.jsx')
const { TeamBoardSkeleton } =
  await server.ssrLoadModule('/src/components/UI/Skeleton.jsx')
const { default: SectionState } =
  await server.ssrLoadModule('/src/components/UI/SectionState.jsx')

const indexCss = await readFile(new URL('../src/index.css', import.meta.url), 'utf8')
const boardSource = await readFile(
  new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
  'utf8',
)
const gameContextSource = await readFile(
  new URL('../src/components/bullpen/board/TeamGameContextCard.jsx', import.meta.url),
  'utf8',
)

function visibleText(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/&#x27;/g, "'")
    .replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim()
}

test('Tailwind consumes the single foundation token authority', () => {
  const foundation = tailwindConfig.theme.extend

  assert.equal(foundation.colors, designTokens.colors)
  assert.equal(foundation.fontSize, designTokens.typography)
  assert.equal(foundation.spacing, designTokens.spacing)
  assert.equal(foundation.screens, designTokens.screens)
  assert.equal(foundation.maxWidth, designTokens.maxWidth)

  const chalkValues = Object.entries(designTokens.colors)
    .filter(([name]) => /^chalk\d+$/.test(name))
    .map(([, value]) => value)
  assert.equal(new Set(chalkValues).size, chalkValues.length)
})

test('foundation exposes named type, rhythm, viewport, and shell scales', () => {
  assert.deepEqual(Object.keys(designTokens.typography), [
    'page-title', 'section-title', 'body', 'compact', 'metadata', 'overline', 'data',
  ])
  assert.deepEqual(designTokens.spacing, {
    meta: '0.375rem',
    row: '0.75rem',
    panel: '1rem',
    pair: '1rem',
    section: '1.5rem',
    'section-lg': '2rem',
  })
  assert.deepEqual(designTokens.screens, {
    phone: '390px', tablet: '768px', desktop: '1280px', wide: '1440px',
  })
  assert.equal(designTokens.maxWidth['team-board'], '90rem')
})

test('Active Arm Row renders backend-provided facts and an accessible handoff', () => {
  const html = renderToStaticMarkup(React.createElement(ActiveArmRow, {
    name: 'Jordan Example',
    roleLabel: 'Setup Arm',
    readLabel: 'On Watch',
    readTone: 'watch',
    lastUsed: 'Yesterday',
    recentWorkload: '28 pitches / 3 days',
    pattern: 'Used on consecutive days',
    href: '/pitchers/42',
  }))
  const text = visibleText(html)

  for (const value of [
    'Jordan Example', 'Setup Arm', 'On Watch', 'Yesterday',
    '28 pitches / 3 days', 'Used on consecutive days', 'View pitcher',
  ]) {
    assert.ok(text.includes(value), `missing ${value}`)
  }
  assert.match(html, /href="\/pitchers\/42"/)
  assert.match(html, /semantic-label--watch/)
  assert.match(html, /min-h-11/)
})

test('Active Arm Row remains partial-safe and does not convert missing facts to zero', () => {
  const html = renderToStaticMarkup(React.createElement(ActiveArmRow, {
    name: 'Partial Example',
    roleLabel: 'Role Unclear',
    readLabel: 'Limited Read',
    readTone: 'limited',
    partialMessage: 'Recent workload metadata was not supplied.',
  }))
  const text = visibleText(html)

  assert.ok(text.includes('Recent workload metadata was not supplied.'))
  assert.equal(/\b0\b/.test(text), false)
  assert.equal(html.includes('href='), false)
})

test('Active Arm Row accepts production facts and preserves legitimate zero values', () => {
  const html = renderToStaticMarkup(React.createElement(ActiveArmRow, {
    name: 'Zero Example',
    roleLabel: 'Backend Role',
    readLabel: 'Backend Read',
    facts: [
      { label: '7D App', value: 0 },
      { label: '7D Pitches', value: 0 },
    ],
    onAction: () => {},
    actionLabel: 'Open pitcher',
    actionAriaLabel: 'Open pitcher context for Zero Example',
  }))

  assert.ok(visibleText(html).includes('7D App 0'))
  assert.ok(visibleText(html).includes('7D Pitches 0'))
  assert.match(html, /<button[^>]*aria-label="Open pitcher context for Zero Example"/)
})

test('Active Arm Row loading state preserves row hierarchy without semantic claims', () => {
  const html = renderToStaticMarkup(React.createElement(ActiveArmRowSkeleton))

  assert.match(html, /role="status"/)
  assert.match(html, /aria-busy="true"/)
  assert.match(html, /active-arm-row/)
  assert.equal(visibleText(html).includes('Fresh'), false)
})

test('Team Board skeleton is hierarchy-preserving and reduced-motion safe', () => {
  const html = renderToStaticMarkup(React.createElement(TeamBoardSkeleton))

  assert.match(html, /data-testid="team-board-skeleton"/)
  assert.match(html, /role="status"/)
  assert.match(html, /aria-busy="true"/)
  assert.match(html, /active-arm-row/)
  assert.match(indexCss, /motion-reduce:animate-none/)
  assert.equal(html.includes('animate-ping'), false)
})

test('Section State preserves independent loaded content and offers a focused retry', () => {
  const html = renderToStaticMarkup(React.createElement(
    SectionState,
    {
      status: 'error',
      title: 'Recent usage unavailable',
      message: 'The current bullpen state remains available.',
      onRetry: () => {},
    },
    React.createElement('p', null, 'Loaded Team State: Fresh'),
  ))
  const text = visibleText(html)

  assert.match(html, /role="alert"/)
  assert.ok(text.includes('Loaded Team State: Fresh'))
  assert.ok(text.includes('Try again'))
  assert.match(html, /min-h-11/)
})

test('semantic styling requires visible supplied text and never authors a label', () => {
  const fresh = renderToStaticMarkup(React.createElement(SemanticLabel, {
    label: 'Fresh', tone: 'fresh',
  }))
  const custom = renderToStaticMarkup(React.createElement(SemanticLabel, {
    label: 'Backend supplied wording', tone: 'invented-tone',
  }))
  const absent = renderToStaticMarkup(React.createElement(SemanticLabel, {
    label: '', tone: 'vulnerable',
  }))

  assert.ok(visibleText(fresh).includes('Fresh'))
  assert.match(fresh, /semantic-label--fresh/)
  assert.ok(visibleText(custom).includes('Backend supplied wording'))
  assert.match(custom, /semantic-label--neutral/)
  assert.equal(absent, '')
})

test('Team Board adopts only the shell and stable loading foundation', () => {
  assert.ok(boardSource.includes('TeamBoardSkeleton'))
  assert.equal(boardSource.includes('LoadingPane'), false)
  assert.equal(boardSource.includes('ActiveArmRow'), false)
  assert.equal(boardSource.includes('SectionState'), false)
})

test('foundation exposes overflow instead of globally hiding it', () => {
  assert.doesNotMatch(indexCss, /body\s*\{[^}]*overflow-x\s*:\s*hidden/s)
  assert.match(indexCss, /\.team-board-shell\s*\{/)
  assert.match(indexCss, /\.active-arm-row\s*\{/)
  assert.match(indexCss, /grid-template-columns:\s*minmax\(12rem, 1\.35fr\)/)
  assert.match(indexCss, /overflow-wrap:\s*anywhere/)
})

test('Team Board foundation does not depend on retired decorative chrome', () => {
  const foundationSources = `${boardSource}\n${gameContextSource}`
  for (const legacyClass of [
    'stadium-glow', 'glow-amber', 'text-gradient-amber',
    'pulse-amber', 'bg-noise', 'border-gradient',
  ]) {
    assert.equal(foundationSources.includes(legacyClass), false, legacyClass)
  }
  assert.equal(indexCss.includes('.glow-amber'), false)
  assert.equal(indexCss.includes('.border-gradient'), false)
})

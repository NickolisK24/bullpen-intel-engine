import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFileSync } from 'node:fs'
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

const { default: Disclosure } = await server.ssrLoadModule('/src/components/UI/Disclosure.jsx')
const boardPageSource = readFileSync('src/components/bullpen/Bullpen.jsx', 'utf8')
const boardSource = readFileSync('src/components/bullpen/board/TonightsBullpenBoard.jsx', 'utf8')

test('Team Board route controls use motionless 44px targets without legacy card chrome', () => {
  const boardModeClasses = boardPageSource.match(/viewMode === BULLPEN_VIEWS\.BOARD\s*\? `([^`]+)`/s)?.[1] || ''
  assert.match(boardModeClasses, /min-h-11/)
  assert.match(boardModeClasses, /border-brand-blue/)
  assert.doesNotMatch(boardModeClasses, /transition|shadow|bg-chalk/)
  assert.match(boardPageSource, /aria-pressed=\{viewMode === m\.id\}/)
})

test('Team Board evidence disclosure is flat, motionless, and touch sized', () => {
  const html = renderToStaticMarkup(React.createElement(
    Disclosure,
    { label: 'Why this read?', hint: 'Evidence and limits', variant: 'flat' },
    React.createElement('p', null, 'Governed evidence.'),
  ))

  assert.match(html, /min-h-11/)
  assert.match(html, /bg-transparent/)
  assert.doesNotMatch(html, /transition|rounded border border-dirt|bg-dugout/)
  assert.match(boardSource, /<BullpenReadDisclosure[\s\S]*?\bflat\b/)
})

test('Team Board share control reuses the shared menu with its bounded flat variant', () => {
  assert.match(boardSource, /<EvidenceShareMenu[\s\S]*?variant="team-board"/)
  assert.equal((boardSource.match(/<EvidenceShareMenu/g) || []).length, 1)
})

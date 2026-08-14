// Public copy pass-through contract (H-5).
//
// Backend semantic owners author public meaning; this layer renders it. These
// tests pin both halves of that split:
//
//   pass-through -- a backend public sentence reaches the reader byte-for-byte,
//                   including words a sanitizer would previously have swapped;
//   fail-closed  -- prohibited or internal framing is REFUSED, not rewritten.
//
// Before this package three components carried chained regex tables that
// rewrote already-authored public copy on its way to the screen
// (Monitor -> On Watch, Avoid -> Unavailable, deterministically -> consistently,
// endpoint -> data feed, and so on). That made the browser a second author of a
// BaseballOS claim, and on the backtest card it meant the blocked-framing guard
// scanned text the browser had already repaired.

import assert from 'node:assert/strict'
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

const { default: BullpenLandscape } = await server.ssrLoadModule(
  '/src/components/dashboard/BullpenLandscape.jsx',
)
const { publicFramingCopy, BLOCKED_FRAMING_COPY_PATTERN } = await server.ssrLoadModule(
  '/src/components/trust/AvailabilityBacktestCard.jsx',
)

const render = (el) => renderToStaticMarkup(el)

const landscapeWith = (notes) => ({
  groups: [
    {
      key: 'rested',
      label: 'Most rested bullpens',
      entries: [{ teamId: 1, label: 'Tigers', count: 5, percentage: 50 }],
    },
  ],
  notes,
  games: { available: true, data_state: 'current', today_count: 8 },
})

// ── pass-through ────────────────────────────────────────────────────────────

test('landscape notes render exactly as the backend authored them', () => {
  const note = 'Groups reflect the current bullpen counts for each team.'
  const html = render(React.createElement(BullpenLandscape, { landscape: landscapeWith([note]) }))
  assert.ok(html.includes(note), 'backend-authored note must render verbatim')
})

test('the landscape does not rewrite words a sanitizer used to swap', () => {
  // If this component ever reinterprets public copy again, these sentences are
  // where it will show: each contains a word the old regex table replaced.
  const notes = [
    'Sorted deterministically by count, then percentage, then team name.',
    'One endpoint reported a stale snapshot.',
    'Monitor arms are restricted and constrained tonight.',
  ]
  const html = render(React.createElement(BullpenLandscape, { landscape: landscapeWith(notes) }))
  for (const note of notes) {
    assert.ok(html.includes(note), `rendered without rewriting: ${note}`)
  }
  // Scope the "nothing invented" check to the note list itself. Words like
  // "On Watch" are legitimate static labels elsewhere in this component, so a
  // whole-document scan would collide with copy this test is not about.
  const renderedNotes = [...html.matchAll(/•\s*([^<]+)</g)].map(match => match[1].trim())
  assert.deepEqual(renderedNotes, notes, 'each note renders byte-for-byte')
  for (const invented of ['consistently', 'data feed', 'BaseballOS service', 'On Watch', 'stretched']) {
    assert.equal(
      renderedNotes.some(note => note.includes(invented)),
      false,
      `frontend must not invent inside a note: ${invented}`,
    )
  }
})

test('backtest framing copy renders verbatim when it is clean', () => {
  const claim =
    'Arms classified Unavailable were used the next day far less often than arms classified Available.'
  assert.equal(publicFramingCopy(claim), claim)
})

test('framing copy no longer rewrites engine vocabulary', () => {
  // The backend authors the reader form now. If a raw engine word ever arrives
  // here, this layer must NOT quietly repair it into publishable copy.
  assert.equal(publicFramingCopy('Arms classified Avoid were used less often.'),
    'Arms classified Avoid were used less often.')
  assert.equal(publicFramingCopy('The usage check ran nightly.'), 'The usage check ran nightly.')
})

// ── fail closed ─────────────────────────────────────────────────────────────

test('prohibited framing is refused, never rewritten', () => {
  for (const banned of [
    'This predicts tomorrow’s usage.',
    'Accuracy was 91% against the model.',
    'Best bet: ride the closer.',
    'Teams are ranked by score.',
    'Computed deterministically from the endpoint snapshot.',
    'COIN V3 governance output.',
  ]) {
    assert.ok(BLOCKED_FRAMING_COPY_PATTERN.test(banned), `must be detected: ${banned}`)
    assert.equal(publicFramingCopy(banned), '', `must be withheld, not repaired: ${banned}`)
  }
})

test('withholding returns empty rather than a substitute sentence', () => {
  const refused = publicFramingCopy('Forecast: three arms unavailable.')
  assert.equal(refused, '')
  assert.equal(refused.length, 0, 'the card falls back to its own fixed copy, not a rewrite')
})

test('ordinary baseball language is not over-refused', () => {
  for (const fine of [
    'Arms classified Unavailable were used the next day far less often.',
    'Observed next-day relief usage on completed games.',
    'Three relievers threw on back-to-back days.',
  ]) {
    assert.equal(publicFramingCopy(fine), fine)
  }
})

// ── no second author remains ────────────────────────────────────────────────

test('no public-copy component carries a vocabulary replacement table', async () => {
  const { readFile } = await import('node:fs/promises')
  const suspects = [
    '../src/components/dashboard/BullpenLandscape.jsx',
    '../src/components/trust/AvailabilityBacktestCard.jsx',
    '../src/components/home/IntelligenceSurface.jsx',
  ]
  // Replacements that swap one governed public word for another. A refusal
  // pattern (a RegExp that gates copy) is allowed; a substitution is not.
  const forbidden = [
    "'On Watch')",
    "'Unavailable')",
    "'stretched')",
    "'Stretched')",
    "'consistently')",
    "'data feed')",
    "'data feeds')",
    "'BaseballOS service')",
    "'usage check')",
    "'Clean Options')",
    "'limited')",
    "'Limited')",
  ]
  for (const relative of suspects) {
    const source = await readFile(new URL(relative, import.meta.url), 'utf8')
    for (const swap of forbidden) {
      assert.equal(
        source.includes(`.replace(`) && source.includes(swap),
        false,
        `${relative} reintroduced a public-vocabulary substitution: ${swap}`,
      )
    }
  }
})

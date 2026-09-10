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

const { default: RecentUsage } = await server.ssrLoadModule(
  '/src/components/bullpen/board/RecentUsage.jsx',
)
const { getRecentUsageView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/recentUsageView.js',
)

const window7 = {
  through: '2026-08-14',
  relief_appearances: 3,
  pitchers_in_relief: 2,
  pitches_total: 81,
  appearances_with_pitches: 3,
  start_relief_unknown: 0,
  sentence: '3 relief appearances in the 7 days through Aug 14.',
  pitchers_sentence: '2 pitchers appeared in relief in the 7 days through Aug 14.',
  pitches_sentence: '81 pitches across those 3 relief appearances.',
}

const payload = {
  windows: { window_7: window7 },
  relief_by_date: [
    { game_date: '2026-08-14', sentence: 'Aug 14 — 4 relief appearances, 3.1 IP, 48 pitches.' },
    { game_date: '2026-08-13', sentence: 'Aug 13 — 1 relief appearance, 1.0 IP, 12 pitches.' },
  ],
}

const render = (props) => renderToStaticMarkup(React.createElement(RecentUsage, props))

test('Recent Usage renders only selected backend-authored window_7 sentences', () => {
  const html = render({ payload })
  assert.ok(html.includes('Recent Usage'))
  assert.ok(html.includes(window7.sentence))
  assert.ok(html.includes(window7.pitchers_sentence))
  assert.ok(html.includes(window7.pitches_sentence))
  assert.ok(html.includes(payload.relief_by_date[0].sentence))
})

test('Recent Usage does not derive totals from appearance rows', () => {
  const served = {
    ...payload,
    relief_by_date: [{
      sentence: payload.relief_by_date[0].sentence,
      appearances: [
        { pitcher_full_name: 'Do Not Summarize', pitches_thrown: 999 },
        { pitcher_full_name: 'Also Hidden', pitches_thrown: 888 },
      ],
    }],
  }
  const html = render({ payload: served })
  assert.equal(html.includes('Do Not Summarize'), false)
  assert.equal(html.includes('999'), false)
  assert.equal(html.includes('1887'), false)
})

test('valid zero-window data remains explicit zero data', () => {
  const zeroWindow = {
    ...window7,
    relief_appearances: 0,
    pitchers_in_relief: 0,
    pitches_total: 0,
    appearances_with_pitches: 0,
    sentence: '0 relief appearances in the 7 days through Aug 14.',
    pitchers_sentence: '0 pitchers appeared in relief in the 7 days through Aug 14.',
    pitches_sentence: '0 pitches across those 0 relief appearances.',
  }
  const html = render({ payload: { windows: { window_7: zeroWindow }, relief_by_date: [] } })
  assert.ok(html.includes(zeroWindow.sentence))
  assert.ok(html.includes(zeroWindow.pitchers_sentence))
  assert.ok(html.includes(zeroWindow.pitches_sentence))
  assert.equal(html.includes('Recent usage unavailable'), false)
  assert.equal(html.includes('Most recent relief work'), false)
})

test('missing or malformed window_7 fails closed instead of becoming zero', () => {
  for (const malformed of [
    null,
    {},
    { windows: {} },
    { windows: { window_7: { ...window7, relief_appearances: '3' } } },
    { windows: { window_7: { ...window7, pitches_total: -1 } } },
    { windows: { window_7: { ...window7, pitches_total: null } } },
    { windows: { window_7: { ...window7, appearances_with_pitches: 2 } } },
    { windows: { window_7: { ...window7, sentence: '' } } },
  ]) {
    const html = render({ payload: malformed })
    assert.ok(html.includes('Recent usage unavailable.'))
    assert.equal(html.includes('0 relief appearances'), false)
    assert.deepEqual(getRecentUsageView(malformed), { available: false })
  }
})

test('partial pitch-count coverage remains verbatim and null never becomes zero', () => {
  const partial = {
    ...window7,
    pitches_total: null,
    appearances_with_pitches: 2,
    pitches_sentence: 'Pitch count unavailable for 1 of 3 relief appearances; 54 pitches across the other 2.',
  }
  const html = render({ payload: { ...payload, windows: { window_7: partial } } })
  assert.ok(html.includes(partial.pitches_sentence))
  assert.equal(html.includes('0 pitches'), false)
})

test('start-relief limitation is shown only when the served count is positive and copy exists', () => {
  const limitation = 'Start/relief status unavailable for 1 of 4 appearances; relief totals cover the other 3.'
  const material = render({ payload: {
    ...payload,
    windows: { window_7: { ...window7, start_relief_unknown: 1, start_relief_unknown_sentence: limitation } },
  } })
  const clean = render({ payload: {
    ...payload,
    windows: { window_7: { ...window7, start_relief_unknown_sentence: limitation } },
  } })
  const missingCopy = render({ payload: {
    ...payload,
    windows: { window_7: { ...window7, start_relief_unknown: 1 } },
  } })
  assert.ok(material.includes(limitation))
  assert.equal(clean.includes(limitation), false)
  assert.equal(missingCopy.includes('start_relief_unknown'), false)
})

test('most recent relief work follows authoritative payload order without sorting', () => {
  const reversed = { ...payload, relief_by_date: [...payload.relief_by_date].reverse() }
  const view = getRecentUsageView(reversed)
  assert.equal(view.mostRecentSentence, payload.relief_by_date[1].sentence)
})

test('loading and error states remain quiet and do not expose raw errors', () => {
  const loading = render({ payload: null, loading: true })
  const error = render({ payload: null, error: 'private network details' })
  assert.ok(loading.includes('Loading recent usage…'))
  assert.ok(error.includes('Recent usage unavailable.'))
  assert.equal(error.includes('private network details'), false)
})

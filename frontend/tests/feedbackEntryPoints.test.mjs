import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFile } from 'node:fs/promises'
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

const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const { default: DataTrust } = await server.ssrLoadModule('/src/components/trust/DataTrust.jsx')

const dashboardSource = await readFile(
  new URL('../src/components/dashboard/Dashboard.jsx', import.meta.url),
  'utf8',
)
const dataTrustSource = await readFile(
  new URL('../src/components/trust/DataTrust.jsx', import.meta.url),
  'utf8',
)
const methodologySource = await readFile(
  new URL('../src/components/methodology/Methodology.jsx', import.meta.url),
  'utf8',
)

const FORMER_FEEDBACK_FORM_URL = 'https://forms.gle/NLCmLEtwJy4qamf77'
const htmlIncludes = (html, text) => html.includes(text)
const inRouter = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)

function assertNoFeedbackEntryPoint(html) {
  for (const text of [
    'Give Feedback',
    'Help shape BaseballOS',
    'Help improve BaseballOS',
    'Questions or feedback on the methodology?',
    FORMER_FEEDBACK_FORM_URL,
  ]) {
    assert.equal(htmlIncludes(html, text), false, text)
  }
}

test('sidebar keeps feedback out of the permanent app rail', () => {
  const html = inRouter(React.createElement(Sidebar))

  assertNoFeedbackEntryPoint(html)
  assert.ok(htmlIncludes(html, 'nav-item'))
  assert.ok(htmlIncludes(html, 'Data Freshness'))
  assert.ok(htmlIncludes(html, 'Page checked'))
  assert.ok(htmlIncludes(html, 'Latest data update'))
  assert.ok(htmlIncludes(html, 'Bullpen data through'))
  assert.ok(!htmlIncludes(html, '>Data through<'))
  assert.ok(!htmlIncludes(html, 'Building BaseballOS in public. Have feedback?'))
})

test('Dashboard and Data & Trust no longer render feedback CTAs', () => {
  const dashboardHtml = inRouter(React.createElement(DashboardView, { data: null, loading: true }))
  const dataTrustHtml = inRouter(React.createElement(DataTrust))

  assertNoFeedbackEntryPoint(dashboardHtml)
  assertNoFeedbackEntryPoint(dataTrustHtml)
  assert.equal(htmlIncludes(dataTrustHtml, 'href="#contact"'), false)
})

test('feedback component wiring is removed from public pages', () => {
  for (const source of [dashboardSource, dataTrustSource, methodologySource]) {
    assert.equal(source.includes('FeedbackCTA'), false)
    assert.equal(source.includes('FeedbackLink'), false)
    assert.equal(source.includes('../feedback/'), false)
    assert.equal(source.includes(FORMER_FEEDBACK_FORM_URL), false)
  }
  assert.equal(methodologySource.includes('Questions or feedback on the methodology?'), false)
  assert.equal(methodologySource.includes('BaseballOS is being refined through real user feedback.'), false)
})

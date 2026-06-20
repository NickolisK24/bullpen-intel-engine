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
const {
  FEEDBACK_FORM_URL,
  FeedbackCTA,
  FeedbackLink,
} = await server.ssrLoadModule('/src/components/feedback/FeedbackLink.jsx')

const methodologySource = await readFile(
  new URL('../src/components/methodology/Methodology.jsx', import.meta.url),
  'utf8',
)

const htmlIncludes = (html, text) => html.includes(text)
const inRouter = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)
const feedbackHref = `href="${FEEDBACK_FORM_URL}"`

function assertSafeExternalFeedbackLink(html) {
  assert.ok(htmlIncludes(html, feedbackHref))
  assert.ok(htmlIncludes(html, 'target="_blank"'))
  assert.ok(htmlIncludes(html, 'rel="noopener noreferrer"'))
}

test('reusable feedback link centralizes the Google Form and safe external attributes', () => {
  const html = renderToStaticMarkup(React.createElement(FeedbackLink))

  assert.ok(htmlIncludes(html, 'Give Feedback'))
  assertSafeExternalFeedbackLink(html)
})

test('sidebar keeps feedback out of the permanent app rail', () => {
  const html = inRouter(React.createElement(Sidebar))
  const linkCount = (html.match(new RegExp(feedbackHref, 'g')) || []).length

  assert.equal(linkCount, 0)
  assert.ok(htmlIncludes(html, 'nav-item'))
  assert.ok(htmlIncludes(html, 'Data Freshness'))
  assert.ok(htmlIncludes(html, 'Last Sync'))
  assert.ok(htmlIncludes(html, 'Data Through'))
  assert.ok(!htmlIncludes(html, 'Building BaseballOS in public. Have feedback?'))
  assert.ok(!htmlIncludes(html, 'Give Feedback'))
})

test('Dashboard includes a non-intrusive feedback CTA', () => {
  const html = inRouter(React.createElement(DashboardView, { data: null, loading: true }))

  assert.ok(htmlIncludes(html, 'Help shape BaseballOS'))
  assert.ok(htmlIncludes(html, 'Share what is useful, unclear, or missing'))
  assertSafeExternalFeedbackLink(html)
})

test('Data & Trust page includes a trust-focused feedback CTA', () => {
  const html = inRouter(React.createElement(DataTrust))

  assert.ok(htmlIncludes(html, 'Help improve BaseballOS'))
  assert.ok(htmlIncludes(html, 'Tell us what works, what does not, and what would make this more useful.'))
  assertSafeExternalFeedbackLink(html)
})

test('Methodology page includes a methodology feedback CTA', () => {
  assert.ok(methodologySource.includes('Questions or feedback on the methodology?'))
  assert.ok(methodologySource.includes('BaseballOS is being refined through real user feedback.'))
  assert.ok(methodologySource.includes('<FeedbackCTA'))

  const html = renderToStaticMarkup(React.createElement(FeedbackCTA, {
    eyebrow: 'Methodology Feedback',
    title: 'Questions or feedback on the methodology?',
    body: 'BaseballOS is being refined through real user feedback.',
  }))

  assert.ok(htmlIncludes(html, 'Questions or feedback on the methodology?'))
  assertSafeExternalFeedbackLink(html)
})

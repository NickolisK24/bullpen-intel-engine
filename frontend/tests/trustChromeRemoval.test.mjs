import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFile } from 'node:fs/promises'
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

const {
  default: BullpenIntelligencePanel,
} = await server.ssrLoadModule('/src/components/observations/BullpenIntelligencePanel.jsx')

const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const forbiddenChrome = /\bCertified\b|\bProtected\b|\bV2\b|\bV3\b|\bV4\b/i

function render(element) {
  return visibleText(renderToStaticMarkup(element))
}

test('trust surfaces do not render certification, protection, or version chrome', () => {
  const observationText = render(
    React.createElement(BullpenIntelligencePanel, {
      state: {
        status: 'fail_closed',
        trustStatus: 'protected',
        observations: [],
        limitations: [],
        confidence: {},
        freshness: {},
      },
    }),
  )

  assert.equal(forbiddenChrome.test(observationText), false, observationText)
  assert.match(observationText, /withheld/i)
})

test('component sources do not contain old visible trust-chrome phrases', async () => {
  const files = [
    '../src/components/explanations/ExplanationDisclosure.jsx',
    '../src/components/observations/BullpenIntelligencePanel.jsx',
  ]
  const oldVisiblePhrases = [
    'Certified V4 Explanation',
    'Freshness Protected',
    'Trust Protected',
    'V2 Bullpen Intelligence',
    'V5 Bullpen Intelligence',
    'Internal / Non-production / Uncertified',
    'Data freshness protection active',
    'Trust protection active',
  ]

  for (const file of files) {
    const source = await readFile(new URL(file, import.meta.url), 'utf8')
    for (const phrase of oldVisiblePhrases) {
      assert.equal(
        source.includes(phrase),
        false,
        `${file} still contains visible trust-chrome phrase: ${phrase}`,
      )
    }
  }
})

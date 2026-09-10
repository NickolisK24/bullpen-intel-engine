import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
test('component sources do not contain old visible trust-chrome phrases', async () => {
  const files = [
    '../src/components/explanations/ExplanationDisclosure.jsx',
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

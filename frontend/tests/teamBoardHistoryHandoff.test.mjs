import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

const appSource = read('../src/App.jsx')
const apiSource = read('../src/utils/api.js')
const boardSource = read('../src/components/bullpen/board/TonightsBullpenBoard.jsx')
const evidenceLinksSource = read('../src/utils/evidenceLinks.js')

test('Team Board omits History when no canonical team-scoped destination exists', () => {
  assert.doesNotMatch(appSource, /path:\s*['"]\/(?:bullpen\/)?history['"]/i)
  assert.doesNotMatch(evidenceLinksSource, /\bHISTORY\s*:/)
  assert.equal(boardSource.includes('<TeamBoardHistory'), false)
  assert.doesNotMatch(boardSource, /coming soon|history unavailable/i)
})

test('omitted History adds no preview request and leaves Relief Work as the final record', () => {
  assert.doesNotMatch(apiSource, /export const getTeamHistory\b/)
  assert.doesNotMatch(boardSource, /getTeamHistory|historyPayload|timelinePayload/)

  const reliefWork = boardSource.indexOf('<TeamReliefWorkPanel')
  const existingShareControls = boardSource.indexOf('<EvidenceShareMenu')
  assert.ok(reliefWork >= 0)
  assert.ok(existingShareControls > reliefWork)
})

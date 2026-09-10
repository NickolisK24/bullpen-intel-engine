import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = relativePath => readFile(new URL(relativePath, import.meta.url), 'utf8')

test('Team Board preserves the approved answer-to-receipts hierarchy', async () => {
  const source = await readSource('../src/components/bullpen/board/TonightsBullpenBoard.jsx')
  const markers = [
    '<TeamBoardAnswerBlock',
    '<TeamBoardActiveBullpen',
    'aria-label="Current workload picture"',
    '<TeamBoardRecentUsage',
    'label="Rest and workload"',
    'label="Roles and performance"',
    'label="Rotation and transactions"',
    '<TeamBoardWhatChanged',
    'aria-label="Relief work receipts"',
    '<TeamReliefWorkPanel',
    '<EvidenceShareMenu',
  ]

  let previous = -1
  for (const marker of markers) {
    const index = source.indexOf(marker)
    assert.ok(index >= 0, `missing Team Board hierarchy marker: ${marker}`)
    assert.ok(index > previous, `Team Board hierarchy marker is out of order: ${marker}`)
    previous = index
  }
})

test('Team Board chapter bands remain mobile-first and do not create paired tablet columns', async () => {
  const boardSource = await readSource('../src/components/bullpen/board/TonightsBullpenBoard.jsx')
  const pairSource = await readSource('../src/components/UI/SectionPair.jsx')

  assert.ok(boardSource.includes('w-screen -translate-x-1/2'))
  assert.ok(boardSource.includes('aria-label="Current workload picture"'))
  assert.ok(boardSource.includes('aria-label="Relief work receipts"'))

  assert.ok(pairSource.includes("'1:1': 'desktop:grid-cols-2'"))
  assert.ok(pairSource.includes("'7:5': 'desktop:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]'"))
  assert.equal(pairSource.includes('tablet:grid-cols-2'), false)
  assert.equal(pairSource.includes('lg:grid-cols-2'), false)
})

test('Team Board keeps Performance secondary and the workload trend as the only governed chart surface', async () => {
  const workloadSource = await readSource('../src/components/bullpen/board/TeamBoardWorkloadOverview.jsx')
  const performanceSource = await readSource('../src/components/bullpen/board/TeamBoardPerformance.jsx')
  const rolesSource = await readSource('../src/components/bullpen/board/TeamBoardRolesDeployment.jsx')

  assert.equal((workloadSource.match(/<WorkloadTrend/g) || []).length, 1)
  assert.ok(performanceSource.includes('Performance unavailable'))
  assert.equal(performanceSource.includes('<svg'), false)
  assert.equal(performanceSource.includes('<canvas'), false)
  assert.equal(performanceSource.includes('chart'), false)

  for (const forbiddenCalculation of ['.reduce(', 'Math.', 'leverage_share', 'role_movement']) {
    assert.equal(rolesSource.includes(forbiddenCalculation), false, forbiddenCalculation)
  }
})

test('Team Board closeout retains accessible focus and truthful withheld-value conventions', async () => {
  const paths = [
    '../src/components/bullpen/board/TonightsBullpenBoard.jsx',
    '../src/components/bullpen/board/TeamBoardActiveBullpen.jsx',
    '../src/components/bullpen/board/TeamBoardRecentUsage.jsx',
    '../src/components/bullpen/board/TeamBoardRecentTransactions.jsx',
  ]
  const sources = await Promise.all(paths.map(readSource))
  const combined = sources.join('\n')

  assert.ok(combined.includes('focus-visible:ring-2'))
  assert.ok(combined.includes('text-text-withheld'))
  assert.equal(combined.includes('animate-pulse'), false)
  assert.equal(combined.includes('animate-spin'), false)
})

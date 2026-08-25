import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appearanceDisplayDate,
  appearanceDetailLabel,
  appearancePitchReason,
  compactAppearanceLabel,
  compactWorkloadAppearanceLabel,
  dayAwareAppearanceReason,
  latestWorkloadAppearanceFromLogs,
  platformDateFromFreshness,
  productCurrentDateFromFreshness,
  relativeAppearanceLabel,
  workloadAppearanceDetailLabel,
} from '../src/utils/appearanceLanguage.js'

test('appearance date equal to current product date renders today', () => {
  const appearance = { game_date: '2026-06-20', pitches: 15 }
  const platformDate = '2026-06-20'

  assert.equal(relativeAppearanceLabel(appearance.game_date, platformDate), 'today')
  assert.equal(appearancePitchReason(15, appearance.game_date, platformDate), '15 pitches today')
  assert.equal(compactAppearanceLabel(appearance, platformDate), 'Last appearance: Today (15)')
  assert.equal(appearanceDetailLabel(appearance, platformDate), 'Jun 20 (Today) • 15 pitches')
})

test('appearance date one calendar day before product date renders yesterday', () => {
  const appearance = { game_date: '2026-06-19', pitches: 21 }
  const platformDate = '2026-06-20'

  assert.equal(relativeAppearanceLabel(appearance.game_date, platformDate), 'yesterday')
  assert.equal(appearancePitchReason(21, appearance.game_date, platformDate), '21 pitches yesterday')
  assert.equal(compactAppearanceLabel(appearance, platformDate), 'Last appearance: Yesterday (21)')
  assert.equal(appearanceDetailLabel(appearance, platformDate), 'Jun 19 (Yesterday) • 21 pitches')
})

test('older appearance dates use days-ago reasons and date fallback displays', () => {
  const appearance = { game_date: '2026-06-14', pitches: 12 }
  const platformDate = '2026-06-20'

  assert.equal(relativeAppearanceLabel(appearance.game_date, platformDate), '6 days ago')
  assert.equal(appearancePitchReason(12, appearance.game_date, platformDate), '12 pitches 6 days ago')
  assert.equal(compactAppearanceLabel(appearance, platformDate), 'Last appearance: Jun 14 (12)')
  assert.equal(appearanceDetailLabel(appearance, platformDate), 'Jun 14 • 12 pitches')
})

test('represented data-through and product-relative labels use separate date authorities', () => {
  const freshness = {
    data_through: '2026-08-24',
    latest_workload_date: '2026-08-24',
    availability_reference_date: '2026-08-25',
    product_current_date: '2026-08-25',
  }
  const representedDate = platformDateFromFreshness(freshness)
  const productDate = productCurrentDateFromFreshness(freshness)
  const rewritten = dayAwareAppearanceReason(
    '15 pitches yesterday',
    { game_date: '2026-08-24', pitches: 15 },
    productDate,
  )

  assert.equal(representedDate, '2026-08-24')
  assert.equal(productDate, '2026-08-25')
  assert.equal(rewritten, '15 pitches yesterday')
  assert.equal(
    workloadAppearanceDetailLabel({ game_date: '2026-08-24', pitches: 15 }, productDate),
    'Aug 24 (Yesterday) • 15 pitches',
  )
})

test('August 25 product date labels only August 25 and August 24 relatively', () => {
  const productDate = '2026-08-25'
  assert.equal(appearanceDisplayDate('2026-08-25', productDate), 'Aug 25 (Today)')
  assert.equal(appearanceDisplayDate('2026-08-24', productDate), 'Aug 24 (Yesterday)')
  assert.equal(appearanceDisplayDate('2026-08-23', productDate), 'Aug 23')
})

test('workload labels use compact workload language for valid appearances', () => {
  const platformDate = '2026-06-20'

  assert.equal(
    compactWorkloadAppearanceLabel({ game_date: '2026-06-20', pitches: 15 }, platformDate),
    'Last workload: Today (15 pitches)',
  )
  assert.equal(
    compactWorkloadAppearanceLabel({ game_date: '2026-06-19', pitches: 21 }, platformDate),
    'Last workload: Yesterday (21 pitches)',
  )
  assert.equal(
    compactWorkloadAppearanceLabel({ game_date: '2026-06-17', pitches: 14 }, platformDate),
    'Last workload: Jun 17 (14 pitches)',
  )
  assert.equal(
    workloadAppearanceDetailLabel({ game_date: '2026-06-17', pitches: 14 }, platformDate),
    'Jun 17 • 14 pitches',
  )
})

test('latest workload appearance skips newer zero-pitch raw rows', () => {
  const logs = [
    {
      game_date: '2026-06-19',
      innings_pitched: 0.0,
      innings_pitched_outs: 0,
      pitches_thrown: 0,
    },
    {
      game_date: '2026-06-17',
      innings_pitched: 1.0,
      innings_pitched_outs: 3,
      pitches_thrown: 14,
    },
  ]

  assert.deepEqual(latestWorkloadAppearanceFromLogs(logs), {
    gameDate: '2026-06-17',
    pitches: 14,
  })
})

test('product current date is accepted only from the backend freshness carrier', () => {
  assert.equal(
    productCurrentDateFromFreshness({ product_current_date: '2026-08-25' }),
    '2026-08-25',
  )
  assert.equal(productCurrentDateFromFreshness({ data_through: '2026-08-24' }), null)
  assert.equal(productCurrentDateFromFreshness({ product_current_date: 'not-a-date' }), null)
  assert.equal(productCurrentDateFromFreshness(null), null)
})

test('relative labels cross month and year boundaries by calendar day', () => {
  assert.equal(appearanceDetailLabel({ game_date: '2026-08-31', pitches: 12 }, '2026-09-01'), 'Aug 31 (Yesterday) • 12 pitches')
  assert.equal(appearanceDetailLabel({ game_date: '2026-12-31', pitches: 13 }, '2027-01-01'), 'Dec 31 (Yesterday) • 13 pitches')
})

test('missing product date fails closed to absolute appearance wording', () => {
  const appearance = { game_date: '2026-08-24', pitches: 15 }
  assert.equal(appearanceDetailLabel(appearance, null), 'Aug 24 • 15 pitches')
  assert.equal(dayAwareAppearanceReason('15 pitches yesterday', appearance, null), '15 pitches on Aug 24')
  assert.equal(relativeAppearanceLabel('2026-08-24', null), null)
})

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appearanceDetailLabel,
  appearancePitchReason,
  compactAppearanceLabel,
  dayAwareAppearanceReason,
  platformDateFromFreshness,
  relativeAppearanceLabel,
} from '../src/utils/appearanceLanguage.js'

test('appearance date equal to current platform date renders today', () => {
  const appearance = { game_date: '2026-06-20', pitches: 15 }
  const platformDate = '2026-06-20'

  assert.equal(relativeAppearanceLabel(appearance.game_date, platformDate), 'today')
  assert.equal(appearancePitchReason(15, appearance.game_date, platformDate), '15 pitches today')
  assert.equal(compactAppearanceLabel(appearance, platformDate), 'Last appearance: Today (15)')
  assert.equal(appearanceDetailLabel(appearance, platformDate), 'Jun 20 (Today) • 15 pitches')
})

test('appearance date one calendar day before platform date renders yesterday', () => {
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

test('same-day evening resync uses data-through date instead of next availability date', () => {
  const freshness = {
    data_through: '2026-06-20',
    latest_workload_date: '2026-06-20',
    availability_reference_date: '2026-06-21',
  }
  const platformDate = platformDateFromFreshness(freshness)
  const rewritten = dayAwareAppearanceReason(
    '15 pitches yesterday',
    { game_date: '2026-06-20', pitches: 15 },
    platformDate,
  )

  assert.equal(platformDate, '2026-06-20')
  assert.equal(rewritten, '15 pitches today')
  assert.notEqual(rewritten, '15 pitches yesterday')
})

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appearanceDetailLabel,
  appearancePitchReason,
  compactAppearanceLabel,
  compactWorkloadAppearanceLabel,
  currentUserBaseballDay,
  dayAwareAppearanceReason,
  latestWorkloadAppearanceFromLogs,
  platformDateFromFreshness,
  relativeAppearanceLabel,
  workloadAppearanceDetailLabel,
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
    last_successful_sync: '2026-06-21T03:03:00Z',
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

test('currentUserBaseballDay returns the user local calendar day and is injectable', () => {
  // Deterministic with an injected Date — this is the anchor for "Today" / "Yesterday".
  assert.equal(currentUserBaseballDay(new Date(2026, 5, 26, 6, 0, 0)), '2026-06-26')
  assert.equal(currentUserBaseballDay(new Date(2026, 0, 3, 23, 59, 0)), '2026-01-03')

  // It is the user's real day, NOT the platform data-through date. On June 26, a June 25
  // workload is one day before today, so it reads "yesterday" against this anchor.
  const userDay = currentUserBaseballDay(new Date(2026, 5, 26))
  assert.equal(userDay, '2026-06-26')
  assert.equal(relativeAppearanceLabel('2026-06-25', userDay), 'yesterday')
  assert.equal(relativeAppearanceLabel('2026-06-26', userDay), 'today')

  // No argument → uses the real current day (a valid YYYY-MM-DD string).
  assert.match(currentUserBaseballDay(), /^\d{4}-\d{2}-\d{2}$/)
  // An invalid date is handled safely.
  assert.equal(currentUserBaseballDay(new Date('not-a-date')), null)
})

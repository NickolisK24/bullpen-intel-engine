// DIST-003 / #594 — the static /team/{ABBR} contract.
//
// The old test proved two files existed. These prove what the files actually
// say: a generated team page either states which baseball date it describes and
// which trusted publication it came from, or it makes no team claim at all.
// Either way it keeps team identity and hands the reader to the live board.

import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import {
  buildTeamSharePath,
  buildTeamShareUrl,
  normalizeTeamShareAbbreviation,
} from '../src/utils/teamShare.js'

const TEAM_ROOT = fileURLToPath(new URL('../public/team/', import.meta.url))
const EXPECTED_TEAM_COUNT = 30
const ISO_DATE = /\b\d{4}-\d{2}-\d{2}\b/

const abbreviations = readdirSync(TEAM_ROOT, { withFileTypes: true })
  .filter(entry => entry.isDirectory())
  .map(entry => entry.name)
  .sort()

const pages = abbreviations.map(abbr => ({
  abbr,
  html: readFileSync(`${TEAM_ROOT}${abbr}/index.html`, 'utf8'),
}))

const fallbackHtml = readFileSync(`${TEAM_ROOT}index.html`, 'utf8')

// The team-shape read labels are backend-owned; read them from the backend
// authority so this assertion cannot drift away from the real vocabulary.
function shapeReadLabels() {
  const source = readFileSync(
    fileURLToPath(new URL('../../backend/services/team_bullpen_shape.py', import.meta.url)),
    'utf8',
  )
  const start = source.indexOf('TEAM_BULLPEN_PUBLIC_LABELS = {')
  assert.ok(start > -1, 'team_bullpen_shape.py no longer declares TEAM_BULLPEN_PUBLIC_LABELS')
  const end = source.slice(start).search(/\r?\n}\r?\n/)
  const block = source.slice(start, end < 0 ? source.length : start + end)
  // Labels are multi-word public strings; the single-word entries are read keys.
  return [...block.matchAll(/'([^']+)'/g)]
    .map(match => match[1])
    .filter(value => /\s/.test(value))
}

function metaContent(html, name) {
  const match = html.match(
    new RegExp(`<meta name="${name.replace(/[:]/g, '[:]')}" content="([^"]*)"`),
  )
  return match ? match[1] : null
}

function propertyContent(html, property) {
  const match = html.match(
    new RegExp(`<meta property="${property.replace(/[:]/g, '[:]')}" content="([^"]*)"`),
  )
  return match ? match[1] : null
}

// Only meaning-bearing values a reader or crawler sees. Structured meta NAMES
// are machine keys, not prose — scanning them would prove nothing.
function readerFacingStrings(html) {
  const values = []
  const title = html.match(/<title>([\s\S]*?)<\/title>/)
  if (title) values.push(title[1])
  for (const name of ['description', 'twitter:title', 'twitter:description']) {
    const value = metaContent(html, name)
    if (value) values.push(value)
  }
  for (const property of ['og:title', 'og:description']) {
    const value = propertyContent(html, property)
    if (value) values.push(value)
  }
  const body = html.match(/<main>([\s\S]*?)<\/main>/)
  if (body) values.push(body[1].replace(/<[^>]*>/g, ' '))
  return values
}

function bodyText(html) {
  const body = html.match(/<main>([\s\S]*?)<\/main>/)
  assert.ok(body, 'page has no crawlable body')
  return body[1].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

test('team share helper builds the canonical pre-rendered team URL', () => {
  assert.equal(normalizeTeamShareAbbreviation({ team_abbreviation: ' tor ' }), 'TOR')
  assert.equal(buildTeamSharePath({ teamAbbreviation: 'sd' }), '/team/SD')
  assert.equal(buildTeamShareUrl({ team_abbreviation: 'TOR' }), 'https://baseballos.app/team/TOR')
  assert.equal(buildTeamShareUrl({ abbr: 'SD' }), 'https://baseballos.app/team/SD')
})

test('every MLB club has a generated page, plus the invalid-team fallback', () => {
  assert.equal(pages.length, EXPECTED_TEAM_COUNT, abbreviations.join(','))
  assert.equal(existsSync(`${TEAM_ROOT}index.html`), true)
  for (const { abbr } of pages) {
    assert.equal(existsSync(`${TEAM_ROOT}${abbr}/index.html`), true, abbr)
  }
})

test('every generated page declares what kind of representation it is', () => {
  for (const { abbr, html } of pages) {
    const representation = metaContent(html, 'baseballos:representation')
    assert.ok(
      representation === 'dated_team_read' || representation === 'withheld',
      `${abbr}: unexpected representation ${representation}`,
    )
    assert.ok(metaContent(html, 'baseballos:generated-at'), `${abbr}: no generated-at`)
    assert.ok(html.includes('<link rel="canonical" '), `${abbr}: no canonical link`)
  }
})

test('a dated read carries its baseball date and the snapshot it came from', () => {
  for (const { abbr, html } of pages) {
    if (metaContent(html, 'baseballos:representation') !== 'dated_team_read') continue

    const dataThrough = metaContent(html, 'baseballos:data-through')
    assert.ok(dataThrough && ISO_DATE.test(dataThrough), `${abbr}: no data-through`)
    assert.ok(metaContent(html, 'baseballos:snapshot-id'), `${abbr}: no snapshot receipt`)

    // The claim a reader sees in an unfurl must itself be dated.
    const description = propertyContent(html, 'og:description')
    assert.ok(description, `${abbr}: no og:description`)
    assert.ok(ISO_DATE.test(description), `${abbr}: undated claim "${description}"`)
    assert.ok(description.includes(dataThrough), `${abbr}: description cites another date`)

    // Publication time is not the baseball date.
    const generatedAt = metaContent(html, 'baseballos:generated-at')
    assert.notEqual(generatedAt, dataThrough, `${abbr}: generated-at used as a baseball date`)
    assert.ok(bodyText(html).includes(dataThrough), `${abbr}: body omits the baseball date`)
  }
})

test('a withheld page carries no date, no receipt, and no present-tense team claim', () => {
  for (const { abbr, html } of pages) {
    if (metaContent(html, 'baseballos:representation') !== 'withheld') continue

    assert.equal(metaContent(html, 'baseballos:data-through'), null, `${abbr}: dated a withheld page`)
    assert.equal(metaContent(html, 'baseballos:snapshot-id'), null, `${abbr}: receipt on a withheld page`)
    assert.ok(metaContent(html, 'baseballos:withheld-reason'), `${abbr}: no withheld reason`)

    const description = propertyContent(html, 'og:description')
    assert.ok(description.startsWith('A dated BaseballOS bullpen read is not published'), abbr)
    for (const label of ['Fresh', 'Stretched', 'Vulnerable']) {
      assert.ok(!new RegExp(`Bullpen: ${label}\\b`).test(html), `${abbr}: state on a withheld page`)
    }
  }
})

test('no generated page states a team condition in a non-canonical vocabulary', () => {
  const labels = shapeReadLabels()
  assert.ok(labels.length >= 20, `expected the shape label catalogue, got ${labels.length}`)

  const offenders = []
  for (const { abbr, html } of [...pages, { abbr: 'fallback', html: fallbackHtml }]) {
    for (const value of readerFacingStrings(html)) {
      for (const label of labels) {
        if (new RegExp(`\\b${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(value)) {
          offenders.push(`${abbr}: ${label}`)
        }
      }
    }
  }
  assert.deepEqual(offenders, [])
})

test('no generated page makes an undated present-tense claim', () => {
  for (const { abbr, html } of pages) {
    const description = propertyContent(html, 'og:description')
    const title = html.match(/<title>([\s\S]*?)<\/title>/)[1]
    if (ISO_DATE.test(description)) continue
    // With no date in the claim, no present-tense team assertion is allowed.
    assert.ok(!/Tonight/i.test(title), `${abbr}: undated "Tonight" title "${title}"`)
    assert.ok(!/Tonight's board/i.test(description), `${abbr}: undated tonight claim`)
    assert.ok(!/bullpen state:/i.test(description), `${abbr}: undated state claim`)
  }
})

test('every generated page keeps a crawlable body and the live board handoff', () => {
  for (const { abbr, html } of pages) {
    const body = bodyText(html)
    assert.ok(body.length > 0, `${abbr}: empty body`)
    assert.ok(body.includes('bullpen board'), `${abbr}: no current-board handoff in the body`)

    const redirect = `/bullpen?view=board&team=${abbr}&source=share`
    assert.ok(
      html.includes(`window.location.replace(${JSON.stringify(redirect)});`),
      `${abbr}: redirect target changed`,
    )
    assert.ok(
      html.includes(`href="/bullpen?view=board&amp;team=${abbr}&amp;source=share"`),
      `${abbr}: no no-script link to the current board`,
    )
    assert.ok(
      html.includes(`<meta property="og:url" content="https://baseballos.app/team/${abbr}" />`),
      `${abbr}: canonical team URL changed`,
    )
  }
})

test('every generated page is accounted for as either a dated read or a withheld one', () => {
  // There is deliberately no assertion that dated pages exist. A run with no
  // trusted publication legitimately withholds every page, and asserting
  // otherwise would turn a correct fail-closed outcome into a red build. What
  // must hold is that the split is total: no page escapes classification, so
  // whichever branch a page lands in, its contract above is enforced.
  const counts = { dated_team_read: 0, withheld: 0 }
  for (const { abbr, html } of pages) {
    const representation = metaContent(html, 'baseballos:representation')
    assert.ok(representation in counts, `${abbr}: unclassified representation`)
    counts[representation] += 1
  }
  assert.equal(counts.dated_team_read + counts.withheld, EXPECTED_TEAM_COUNT)
})

test('the invalid-team fallback still makes no team claim', () => {
  assert.equal(metaContent(fallbackHtml, 'baseballos:representation'), 'invalid_team')
  assert.equal(metaContent(fallbackHtml, 'baseballos:data-through'), null)
  assert.equal(ISO_DATE.test(fallbackHtml), false)
  assert.ok(fallbackHtml.includes('window.location.replace("/");'))
  assert.ok(
    bodyText(fallbackHtml).includes(
      'Open BaseballOS for current bullpen availability and trust reads.',
    ),
  )
})

test('stories use the bounded link-only menu without fetching card data', () => {
  const source = readFileSync('src/components/stories/Stories.jsx', 'utf8')
  const menu = readFileSync('src/components/share/EvidenceShareMenu.jsx', 'utf8')
  assert.ok(source.includes('EvidenceShareMenu'))
  assert.ok(source.includes('linkOnly'))
  assert.ok(source.includes('destinationUrl={`${EVIDENCE_CARD_ORIGIN}${story.href}`}'))
  assert.equal(menu.includes('/bullpen/teams/'), false)
  assert.equal(menu.includes('fetch('), false)
})

test('Team card fail-closed state withholds every published-citation action', () => {
  const menu = readFileSync('src/components/share/EvidenceShareMenu.jsx', 'utf8')
  assert.ok(menu.includes("disabled={busy || (typeof loadCardModel === 'function' && !cardAvailable) || (!linkOnly && !cardAvailable)}"))
  assert.ok(menu.includes('Copy published link'))
  assert.equal(menu.includes("disabled={busy}\n            onClick={() => run('copy')}"), false)
})

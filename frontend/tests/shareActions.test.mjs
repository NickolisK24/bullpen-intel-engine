import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})
after(async () => server.close())

const share = await server.ssrLoadModule('/src/utils/shareActions.js')

const destinationUrl = 'https://baseballos.app/bullpen?view=compare&team_a=NYY&team_b=BOS#comparison-evidence'
const context = {
  surface: 'compare_bullpens',
  cardType: 'comparison',
  team_a_ref: 'NYY',
  team_b_ref: 'BOS',
  evidence_target: 'comparison_evidence',
  data_through: '2026-07-14',
}
const model = { destinationUrl, fileName: 'baseballos-nyy-vs-bos-2026-07-14.png' }

function identityOptions(calls = []) {
  let id = 0
  return {
    storage: {
      values: new Map(),
      getItem(key) { return this.values.get(key) || null },
      setItem(key, value) { this.values.set(key, value) },
    },
    cryptoObject: { randomUUID: () => `00000000-0000-4000-8000-${String(++id).padStart(12, '0')}` },
    now: 1_700_000_000_000,
    configuredBackendOrigin: 'https://api.baseballos.app',
    fetchImpl: async (url, options) => { calls.push({ url, options }); return { ok: true } },
    renderPng: async () => new Blob(['png'], { type: 'image/png' }),
  }
}

test('exact share URLs preserve the destination and add only the bounded source', () => {
  assert.equal(
    share.buildExactShareUrl('https://baseballos.app/bullpen?view=board&team=NYY#team-relief-work'),
    'https://baseballos.app/bullpen?view=board&team=NYY&source=share_link#team-relief-work',
  )
  assert.equal(
    share.buildExactShareUrl(destinationUrl),
    'https://baseballos.app/bullpen?view=compare&team_a=NYY&team_b=BOS&source=share_link#comparison-evidence',
  )
  assert.equal(
    share.buildExactShareUrl(destinationUrl, share.PUBLIC_SHARE_ORIGIN, 'share_card'),
    'https://baseballos.app/bullpen?view=compare&team_a=NYY&team_b=BOS&source=share_card#comparison-evidence',
  )
  assert.equal(share.buildExactShareUrl('https://example.com/bullpen'), null)
  assert.equal(share.buildExactShareUrl('/stories'), null)
  assert.equal(share.buildExactShareUrl('/bullpen?view=board&team=NYY&campaign=unbounded'), null)
})

test('native card share uses file capability and records only after completion', async () => {
  const calls = []
  class FakeFile { constructor(parts, name, options) { this.name = name; this.type = options.type } }
  const env = {
    File: FakeFile,
    localStorage: identityOptions().storage,
    navigator: {
      canShare: payload => payload.files[0].name === model.fileName,
      share: async payload => calls.push({ shared: payload }),
    },
  }
  const options = identityOptions(calls)
  options.storage = env.localStorage
  const result = await share.shareEvidenceCard({ model, shareText: 'Current bullpen comparison', context }, env, options)
  assert.equal(result.status, 'shared_card')
  assert.match(result.url, /source=share_card/)
  const recorded = calls.find(call => call.url)
  assert.equal(recorded.url, 'https://api.baseballos.app/api/traffic/share-action')
  assert.equal(JSON.parse(recorded.options.body).action, 'native_card_share')
})

test('card share falls back to a native exact link and records that method', async () => {
  const calls = []
  const env = {
    File: class {},
    localStorage: identityOptions().storage,
    navigator: { canShare: () => false, share: async payload => calls.push({ shared: payload }) },
  }
  const options = identityOptions(calls)
  options.storage = env.localStorage
  const result = await share.shareEvidenceCard({ model, context }, env, options)
  assert.equal(result.status, 'shared_link')
  assert.match(result.url, /source=share_link/)
  assert.equal(JSON.parse(calls.find(call => call.url).options.body).action, 'native_link_share')
})

test('cancelled and failed card actions do not record completion', async () => {
  const cancelledCalls = []
  const error = new Error('cancelled')
  error.name = 'AbortError'
  const cancelled = await share.shareEvidenceCard(
    { model, context },
    { File: class {}, localStorage: identityOptions().storage, navigator: { canShare: () => true, share: async () => { throw error } } },
    identityOptions(cancelledCalls),
  )
  assert.equal(cancelled.status, 'cancelled')
  assert.equal(cancelledCalls.length, 0)

  const failedCalls = []
  const failed = await share.shareEvidenceCard(
    { model, context },
    { navigator: {} },
    { ...identityOptions(failedCalls), renderPng: async () => { throw new Error('render failed') } },
  )
  assert.equal(failed.status, 'generation_failed')
  assert.equal(failedCalls.length, 0)
})

test('copy and download record completed actions while measurement failure stays fail-soft', async () => {
  const calls = []
  const storage = identityOptions().storage
  const copyResult = await share.copyExactLink(
    { destinationUrl, context },
    { localStorage: storage, navigator: { clipboard: { writeText: async value => calls.push({ copied: value }) } } },
    { ...identityOptions(calls), storage },
  )
  assert.equal(copyResult.status, 'copied')
  assert.equal(JSON.parse(calls.find(call => call.url).options.body).action, 'copy_link')

  const documentCalls = []
  const downloadResult = await share.downloadEvidenceCard(
    { model, context },
    {
      localStorage: storage,
      document: { createElement: () => ({ click: () => documentCalls.push('click') }) },
      URL: { createObjectURL: () => 'blob:png', revokeObjectURL: value => documentCalls.push(value) },
    },
    { ...identityOptions(), storage, fetchImpl: async () => { throw new Error('offline') } },
  )
  assert.equal(downloadResult.status, 'downloaded')
  assert.deepEqual(documentCalls, ['click', 'blob:png'])
})

test('payload contains only bounded identity and context fields', () => {
  const payload = share.buildShareActionPayload(context, 'copy_link', identityOptions())
  assert.deepEqual(Object.keys(payload).sort(), [
    'action', 'card_type', 'data_through', 'event_id', 'evidence_target',
    'session_id', 'site_host', 'surface', 'team_a_ref', 'team_b_ref', 'visitor_id',
  ])
  assert.equal(payload.card_type, 'comparison')
  assert.equal('url' in payload, false)
  assert.equal('recipient' in payload, false)
  assert.equal('platform' in payload, false)
})

test('share menu keeps one in-flight action and exposes accessibility behavior', async () => {
  const source = await import('node:fs').then(fs => fs.readFileSync('src/components/share/EvidenceShareMenu.jsx', 'utf8'))
  for (const contract of [
    'aria-label="Open evidence sharing options"', 'aria-haspopup="menu"',
    'aria-live="polite"', "event.key === 'Escape'", "document.addEventListener('focusin'",
    "document.addEventListener('pointerdown'", 'if (busyRef.current) return',
    'Card unavailable until a current evidence-backed read is available.',
  ]) assert.ok(source.includes(contract), contract)
})

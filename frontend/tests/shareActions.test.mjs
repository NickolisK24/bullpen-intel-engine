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
const storyModel = {
  destinationUrl,
  fileName: 'baseballos-nyy-vs-bos-2026-07-14.png',
  cardVersion: 'comparison_story_v2',
  storyAngle: 'comparison_availability',
}

function recordedBody(calls) {
  return JSON.parse(calls.find(call => call.url).options.body)
}

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

test('native card share attaches the card model version and story angle', async () => {
  const calls = []
  class FakeFile { constructor(parts, name, options) { this.name = name; this.type = options.type } }
  const env = {
    File: FakeFile,
    localStorage: identityOptions().storage,
    navigator: {
      canShare: payload => payload.files[0].name === storyModel.fileName,
      share: async payload => calls.push({ shared: payload }),
    },
  }
  const options = identityOptions(calls)
  options.storage = env.localStorage
  const result = await share.shareEvidenceCard({ model: storyModel, shareText: 'observation', context }, env, options)
  assert.equal(result.status, 'shared_card')
  const body = recordedBody(calls)
  assert.equal(body.action, 'native_card_share')
  assert.equal(body.card_version, 'comparison_story_v2')
  assert.equal(body.story_angle, 'comparison_availability')
})

test('native-link fallback from a generated card still carries the story fields', async () => {
  const calls = []
  const env = {
    File: class {},
    localStorage: identityOptions().storage,
    navigator: { canShare: () => false, share: async payload => calls.push({ shared: payload }) },
  }
  const options = identityOptions(calls)
  options.storage = env.localStorage
  const result = await share.shareEvidenceCard({ model: storyModel, context }, env, options)
  assert.equal(result.status, 'shared_link')
  const body = recordedBody(calls)
  assert.equal(body.action, 'native_link_share')
  assert.equal(body.card_version, 'comparison_story_v2')
  assert.equal(body.story_angle, 'comparison_availability')
})

test('copy-link and card download from a generated card carry the story fields', async () => {
  const copyCalls = []
  const storage = identityOptions().storage
  const copyResult = await share.copyExactLink(
    { destinationUrl, context, cardModel: storyModel },
    { localStorage: storage, navigator: { clipboard: { writeText: async () => copyCalls.push('copied') } } },
    { ...identityOptions(copyCalls), storage },
  )
  assert.equal(copyResult.status, 'copied')
  const copyBody = recordedBody(copyCalls)
  assert.equal(copyBody.action, 'copy_link')
  assert.equal(copyBody.card_version, 'comparison_story_v2')
  assert.equal(copyBody.story_angle, 'comparison_availability')

  const downloadCalls = []
  const downloadResult = await share.downloadEvidenceCard(
    { model: storyModel, context },
    {
      localStorage: storage,
      document: { createElement: () => ({ click: () => {} }) },
      URL: { createObjectURL: () => 'blob:png', revokeObjectURL: () => {} },
    },
    { ...identityOptions(downloadCalls), storage },
  )
  assert.equal(downloadResult.status, 'downloaded')
  const downloadBody = recordedBody(downloadCalls)
  assert.equal(downloadBody.action, 'download_card')
  assert.equal(downloadBody.card_version, 'comparison_story_v2')
  assert.equal(downloadBody.story_angle, 'comparison_availability')
})

test('the card model overrides conflicting caller-supplied story context', async () => {
  const calls = []
  const storage = identityOptions().storage
  const spoofedContext = { ...context, card_version: 'team_story_v2', story_angle: 'starter_support' }
  await share.copyExactLink(
    { destinationUrl, context: spoofedContext, cardModel: storyModel },
    { localStorage: storage, navigator: { clipboard: { writeText: async () => {} } } },
    { ...identityOptions(calls), storage },
  )
  const body = recordedBody(calls)
  assert.equal(body.card_version, 'comparison_story_v2')
  assert.equal(body.story_angle, 'comparison_availability')
})

test('withCardStoryContext returns a new object, omits fields without a model, and never mutates inputs', () => {
  const base = { surface: 'bullpen_board', cardType: 'team', card_version: 'stale', story_angle: 'stale' }
  const withModel = share.withCardStoryContext(base, { cardVersion: 'team_story_v2', storyAngle: 'availability_constraint' })
  assert.equal(withModel.card_version, 'team_story_v2')
  assert.equal(withModel.story_angle, 'availability_constraint')
  assert.notEqual(withModel, base)
  // Caller-supplied fields are stripped when there is no model.
  const withoutModel = share.withCardStoryContext(base, null)
  assert.equal('card_version' in withoutModel, false)
  assert.equal('story_angle' in withoutModel, false)
  // A model missing one half of the pair attaches neither.
  const partial = share.withCardStoryContext(base, { cardVersion: 'team_story_v2' })
  assert.equal('card_version' in partial, false)
  assert.equal('story_angle' in partial, false)
  // Inputs are not mutated.
  assert.equal(base.card_version, 'stale')
})

test('no card model means the story fields are omitted from the payload', () => {
  const withModel = share.buildShareActionPayload(
    share.withCardStoryContext(context, storyModel), 'copy_link', identityOptions(),
  )
  assert.equal(withModel.card_version, 'comparison_story_v2')
  assert.equal(withModel.story_angle, 'comparison_availability')
  const withoutModel = share.buildShareActionPayload(
    share.withCardStoryContext(context, null), 'copy_link', identityOptions(),
  )
  assert.equal('card_version' in withoutModel, false)
  assert.equal('story_angle' in withoutModel, false)
})

test('story-context payloads still exclude URL, headline, receipts, share text, recipient, and platform', () => {
  const payload = share.buildShareActionPayload(
    share.withCardStoryContext({
      ...context,
      headline: 'NYY HAVE MORE',
      supportingLine: 'context',
      receipts: ['a', 'b'],
      shareText: 'text',
      destinationUrl,
      recipient: 'fan@example.com',
      platform: 'social',
    }, storyModel),
    'copy_link',
    identityOptions(),
  )
  assert.deepEqual(Object.keys(payload).sort(), [
    'action', 'card_type', 'card_version', 'data_through', 'event_id', 'evidence_target',
    'session_id', 'site_host', 'story_angle', 'surface', 'team_a_ref', 'team_b_ref', 'visitor_id',
  ])
  for (const key of ['headline', 'supportingLine', 'receipts', 'shareText', 'destinationUrl', 'url', 'recipient', 'platform']) {
    assert.equal(key in payload, false, key)
  }
})

test('cancelled and failed story-card actions still record nothing', async () => {
  const cancelledCalls = []
  const error = new Error('cancelled')
  error.name = 'AbortError'
  const cancelled = await share.shareEvidenceCard(
    { model: storyModel, context },
    { File: class {}, localStorage: identityOptions().storage, navigator: { canShare: () => true, share: async () => { throw error } } },
    identityOptions(cancelledCalls),
  )
  assert.equal(cancelled.status, 'cancelled')
  assert.equal(cancelledCalls.length, 0)
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

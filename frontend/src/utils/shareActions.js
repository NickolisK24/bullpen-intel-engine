import { readAuthToken } from './api'
import {
  getOrCreateSession,
  getOrCreateVisitorId,
  TRAFFIC_CANONICAL_HOST,
} from './trafficMeasurement'
import { renderEvidenceCardPng } from './evidenceCardRenderer'
import {
  BULLPEN_VIEWS,
  buildCanonicalBullpenHref,
  normalizeTeamReference,
  readBullpenLocation,
} from './evidenceLinks'

export const SHARE_ACTION_PATH = '/traffic/share-action'
export const PUBLIC_SHARE_ORIGIN = 'https://baseballos.app'

function uuid(cryptoObject = globalThis.crypto) {
  if (!cryptoObject || typeof cryptoObject.randomUUID !== 'function') return null
  return cryptoObject.randomUUID()
}

export function buildExactShareUrl(
  destinationUrl,
  origin = PUBLIC_SHARE_ORIGIN,
  entrySource = 'share_link',
) {
  try {
    const url = new URL(destinationUrl, origin)
    if (url.origin !== PUBLIC_SHARE_ORIGIN || url.pathname !== '/bullpen') return null
    if (!['share_link', 'share_card'].includes(entrySource)) return null
    const state = readBullpenLocation(url.search, url.hash)
    if (state.requestedView !== state.view || state.unsupportedHash) return null
    const allowedKeys = state.view === BULLPEN_VIEWS.COMPARE
      ? new Set(['view', 'team_a', 'team_b', 'source'])
      : new Set(['view', 'team', 'pitcher', 'source'])
    if ([...url.searchParams.keys()].some(key => !allowedKeys.has(key))) return null
    if (state.view === BULLPEN_VIEWS.COMPARE) {
      const teamA = normalizeTeamReference(state.teamA)
      const teamB = normalizeTeamReference(state.teamB)
      if (!teamA || !teamB || teamA === teamB) return null
    } else if (state.view === BULLPEN_VIEWS.BOARD) {
      if (!normalizeTeamReference(state.team)) return null
    } else {
      return null
    }
    return `${PUBLIC_SHARE_ORIGIN}${buildCanonicalBullpenHref({ ...state, source: entrySource })}`
  } catch {
    return null
  }
}

// Combine the bounded caller context with the generated card model's story
// metadata. The card model is the authority: it strips any caller-supplied
// story fields and, when both are present, attaches its own bounded pair.
// Returns a new object and never mutates its arguments.
export function withCardStoryContext(context, cardModel = null) {
  const merged = { ...(context || {}) }
  delete merged.card_version
  delete merged.story_angle
  const cardVersion = cardModel?.cardVersion
  const storyAngle = cardModel?.storyAngle
  if (cardVersion && storyAngle) {
    merged.card_version = cardVersion
    merged.story_angle = storyAngle
  }
  return merged
}

export function buildShareActionPayload(context, action, {
  storage,
  now = Date.now(),
  cryptoObject = globalThis.crypto,
} = {}) {
  const eventId = uuid(cryptoObject)
  const visitorId = getOrCreateVisitorId(storage, cryptoObject)
  const session = getOrCreateSession(storage, now, cryptoObject)
  if (!eventId || !visitorId || !session || !context) return null
  const payload = {
    event_id: eventId,
    visitor_id: visitorId,
    session_id: session.session_id,
    surface: context.surface,
    card_type: context.cardType,
    action,
    site_host: TRAFFIC_CANONICAL_HOST,
  }
  for (const key of [
    'team_ref', 'team_a_ref', 'team_b_ref', 'evidence_target', 'data_through',
    'card_version', 'story_angle',
  ]) {
    if (context[key] != null && context[key] !== '') payload[key] = context[key]
  }
  return payload
}

export function shareActionUrl(configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL) {
  const apiBase = configuredBackendOrigin ? `${configuredBackendOrigin}/api` : '/api'
  return `${apiBase}${SHARE_ACTION_PATH}`
}

export async function recordCompletedShareAction(context, action, {
  fetchImpl = globalThis.fetch,
  storage,
  now,
  cryptoObject,
  configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL,
} = {}) {
  const payload = buildShareActionPayload(context, action, { storage, now, cryptoObject })
  if (!payload || typeof fetchImpl !== 'function') return
  const headers = { 'Content-Type': 'application/json' }
  const token = readAuthToken(storage)
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    await fetchImpl(shareActionUrl(configuredBackendOrigin), {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      keepalive: true,
    })
  } catch {
    // Completed user actions remain successful when measurement is unavailable.
  }
}

function isCancel(error) {
  return ['AbortError', 'NotAllowedError'].includes(error?.name)
}

async function copyText(value, env) {
  if (env?.navigator?.clipboard?.writeText) {
    await env.navigator.clipboard.writeText(value)
    return true
  }
  const documentRef = env?.document
  if (!documentRef?.createElement || !documentRef?.body?.appendChild) return false
  const input = documentRef.createElement('textarea')
  input.value = value
  input.setAttribute('readonly', '')
  input.style.position = 'fixed'
  input.style.top = '-9999px'
  documentRef.body.appendChild(input)
  input.select()
  try {
    return Boolean(documentRef.execCommand?.('copy'))
  } finally {
    documentRef.body.removeChild(input)
  }
}

async function measure(context, action, options) {
  await recordCompletedShareAction(context, action, options)
}

export async function copyExactLink({ destinationUrl, context, cardModel = null }, env = globalThis, options = {}) {
  const url = buildExactShareUrl(destinationUrl)
  if (!url) return { status: 'unavailable' }
  const storyContext = withCardStoryContext(context, cardModel)
  try {
    if (!await copyText(url, env)) return { status: 'unavailable', url }
    await measure(storyContext, 'copy_link', { ...options, storage: options.storage || env.localStorage })
    return { status: 'copied', url }
  } catch {
    return { status: 'unavailable', url }
  }
}

export async function shareExactLink({ destinationUrl, shareText, context, cardModel = null }, env = globalThis, options = {}) {
  const url = buildExactShareUrl(destinationUrl)
  if (!url) return { status: 'unavailable' }
  const storyContext = withCardStoryContext(context, cardModel)
  if (typeof env?.navigator?.share === 'function') {
    try {
      await env.navigator.share({ text: shareText, url })
      await measure(storyContext, 'native_link_share', { ...options, storage: options.storage || env.localStorage })
      return { status: 'shared_link', url }
    } catch (error) {
      if (isCancel(error)) return { status: 'cancelled', url }
      return { status: 'unavailable', url }
    }
  }
  return copyExactLink({ destinationUrl, context, cardModel }, env, options)
}

export async function shareEvidenceCard({ model, shareText, context }, env = globalThis, options = {}) {
  if (!model) return { status: 'unavailable' }
  let blob
  try {
    blob = await (options.renderPng || renderEvidenceCardPng)(model, env)
  } catch {
    return { status: 'generation_failed' }
  }

  const cardUrl = buildExactShareUrl(model.destinationUrl, PUBLIC_SHARE_ORIGIN, 'share_card')
  const linkUrl = buildExactShareUrl(model.destinationUrl)
  if (!cardUrl || !linkUrl) return { status: 'unavailable' }
  const storyContext = withCardStoryContext(context, model)
  const FileCtor = env?.File
  const nav = env?.navigator
  let file = null
  if (FileCtor) {
    try {
      file = new FileCtor([blob], model.fileName, { type: 'image/png' })
    } catch {
      file = null
    }
  }

  if (file && typeof nav?.share === 'function') {
    let canShareFiles = false
    try {
      canShareFiles = typeof nav.canShare === 'function' && nav.canShare({ files: [file] })
    } catch {
      canShareFiles = false
    }
    if (canShareFiles) {
      try {
        await nav.share({ files: [file], text: shareText, url: cardUrl })
        await measure(storyContext, 'native_card_share', { ...options, storage: options.storage || env.localStorage })
        return { status: 'shared_card', url: cardUrl }
      } catch (error) {
        return { status: isCancel(error) ? 'cancelled' : 'unavailable', url: cardUrl }
      }
    }
  }

  if (typeof nav?.share === 'function') {
    try {
      await nav.share({ text: shareText, url: linkUrl })
      await measure(storyContext, 'native_link_share', { ...options, storage: options.storage || env.localStorage })
      return { status: 'shared_link', url: linkUrl }
    } catch (error) {
      return { status: isCancel(error) ? 'cancelled' : 'unavailable', url: linkUrl }
    }
  }
  return copyExactLink({ destinationUrl: model.destinationUrl, context, cardModel: model }, env, options)
}

export async function downloadEvidenceCard({ model, context }, env = globalThis, options = {}) {
  if (!model) return { status: 'unavailable' }
  let blob
  try {
    blob = await (options.renderPng || renderEvidenceCardPng)(model, env)
  } catch {
    return { status: 'generation_failed' }
  }
  const documentRef = env?.document
  const urlApi = env?.URL
  if (!documentRef?.createElement || !urlApi?.createObjectURL) return { status: 'unavailable' }
  const storyContext = withCardStoryContext(context, model)
  const objectUrl = urlApi.createObjectURL(blob)
  try {
    const anchor = documentRef.createElement('a')
    anchor.href = objectUrl
    anchor.download = model.fileName
    anchor.rel = 'noopener'
    anchor.click()
    await measure(storyContext, 'download_card', { ...options, storage: options.storage || env.localStorage })
    return { status: 'downloaded', fileName: model.fileName }
  } catch {
    return { status: 'unavailable' }
  } finally {
    urlApi.revokeObjectURL(objectUrl)
  }
}

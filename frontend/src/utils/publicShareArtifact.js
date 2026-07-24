// Public Share Artifact read util (Share Cards SC-04).
//
// Fetches the permanent public artifact read from the PUBLIC, unauthenticated
// endpoint only. It never attaches an auth/admin token, never calls an
// internal/admin endpoint, never requests current/live team state, and never
// invokes generation. It maps the lifecycle-aware HTTP contract to honest UI
// states so the page can render truthfully.

export const PUBLIC_SHARE_ROUTE = '/share/:publicId'

export function publicSharePath(publicId) {
  return `/share/${encodeURIComponent(publicId ?? '')}`
}

export const SHARE_STATE = {
  LOADING: 'loading',
  OK: 'ok',
  SUPERSEDED: 'superseded',
  WITHDRAWN: 'withdrawn',
  NOT_FOUND: 'not_found',
  INTEGRITY_ERROR: 'integrity_error',
  API_ERROR: 'api_error',
}

function publicArtifactUrl(publicId, configuredBackendOrigin) {
  const apiBase = configuredBackendOrigin ? `${configuredBackendOrigin}/api` : '/api'
  return `${apiBase}/share-artifacts/${encodeURIComponent(publicId)}`
}

export async function fetchPublicShareArtifact(publicId, {
  fetchImpl = globalThis.fetch,
  configuredBackendOrigin = (typeof import.meta !== 'undefined' ? import.meta.env?.VITE_API_BASE_URL : undefined),
} = {}) {
  if (!publicId) return { state: SHARE_STATE.NOT_FOUND }

  let response
  try {
    // GET only, no credentials, no auth header — a published artifact is public.
    response = await fetchImpl(publicArtifactUrl(publicId, configuredBackendOrigin), {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
  } catch {
    return { state: SHARE_STATE.API_ERROR }
  }

  let body = null
  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (response.status === 200) {
    const state = body?.status === 'superseded' ? SHARE_STATE.SUPERSEDED : SHARE_STATE.OK
    return { state, artifact: body?.artifact ?? null }
  }
  if (response.status === 410) return { state: SHARE_STATE.WITHDRAWN, artifact: body?.artifact ?? null }
  if (response.status === 404) return { state: SHARE_STATE.NOT_FOUND }
  if (response.status === 503) return { state: SHARE_STATE.INTEGRITY_ERROR }
  return { state: SHARE_STATE.API_ERROR }
}

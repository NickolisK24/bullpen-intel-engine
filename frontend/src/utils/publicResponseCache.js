const DEFAULT_MAX_ENTRIES = 64

function nowMs() {
  return Date.now()
}

function normalizeIdentity(payload) {
  const identity = payload?.publication_identity || payload?.snapshot || payload?.identity || null
  if (!identity || identity.snapshot_id == null) return null
  return {
    snapshot_id: identity.snapshot_id,
    sync_run_id: identity.sync_run_id ?? null,
    represented_date: identity.represented_date ?? identity.data_through ?? null,
    payload_version: identity.payload_version ?? payload?.version ?? payload?.contract_version ?? null,
    source_revision: identity.source_revision ?? null,
  }
}

export function publicationIdentityKey(payload) {
  const identity = normalizeIdentity(payload)
  if (!identity) return null
  return [
    identity.snapshot_id,
    identity.sync_run_id ?? '',
    identity.represented_date ?? '',
    identity.payload_version ?? '',
    identity.source_revision ?? '',
  ].join(':')
}

export function isReusablePublicPayload(payload) {
  if (!payload || typeof payload !== 'object') return false
  const status = String(payload.status || '').toLowerCase()
  if (['unavailable', 'snapshot_unavailable', 'partial', 'identity_mismatch'].includes(status)) {
    return false
  }
  return status === '' || ['ok', 'available', 'empty'].includes(status)
}

export function createPublicResponseCache({ maxEntries = DEFAULT_MAX_ENTRIES, clock = nowMs } = {}) {
  const entries = new Map()
  const aliases = new Map()

  function touch(key, entry) {
    entries.delete(key)
    entries.set(key, entry)
  }

  function evict() {
    while (entries.size > maxEntries) {
      const oldest = entries.keys().next().value
      entries.delete(oldest)
      for (const [alias, target] of aliases) {
        if (target.key === oldest) aliases.delete(alias)
      }
    }
  }

  function get(aliasKey) {
    const alias = aliases.get(aliasKey)
    if (!alias || alias.expiresAt <= clock()) {
      if (alias) aliases.delete(aliasKey)
      return null
    }
    const entry = entries.get(alias.key)
    if (!entry || entry.expiresAt <= clock()) {
      aliases.delete(aliasKey)
      if (entry) entries.delete(alias.key)
      return null
    }
    touch(alias.key, entry)
    return entry.payload
  }

  function set(aliasKey, payload, { ttlMs, immutableTtlMs = ttlMs, identityKey } = {}) {
    if (!isReusablePublicPayload(payload)) return payload
    const ttl = Math.max(0, Number(ttlMs) || 0)
    if (ttl === 0) return payload
    const stableIdentity = identityKey || publicationIdentityKey(payload)
    const entryKey = stableIdentity ? `${aliasKey}|publication:${stableIdentity}` : aliasKey
    const entryTtl = stableIdentity ? Math.max(ttl, Number(immutableTtlMs) || ttl) : ttl
    entries.set(entryKey, { payload, expiresAt: clock() + entryTtl })
    aliases.set(aliasKey, { key: entryKey, expiresAt: clock() + ttl })
    evict()
    return payload
  }

  function clear() {
    entries.clear()
    aliases.clear()
  }

  return {
    clear,
    get,
    set,
    size: () => entries.size,
    aliasSize: () => aliases.size,
  }
}

export const publicResponseCache = createPublicResponseCache()

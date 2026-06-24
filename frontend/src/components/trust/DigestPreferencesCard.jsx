import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { usePreferredTeamPreference } from '../../hooks/usePreferredTeamPreference'
import {
  getDigestPreferences,
  getTeams,
  updateDigestPreferences,
} from '../../utils/api'
import { preferredTeamLabel } from '../../utils/preferredTeam'

export const DIGEST_SAVE_IDLE = 'idle'
export const DIGEST_SAVE_LOADING = 'loading'
export const DIGEST_SAVE_SAVED = 'saved'
export const DIGEST_SAVE_ERROR = 'error'

const VALID_CADENCES = new Set(['daily', 'weekly', 'off'])

function cleanCadence(value) {
  const cadence = String(value || '').trim().toLowerCase()
  return VALID_CADENCES.has(cadence) ? cadence : 'daily'
}

function isDigestEnabled(value) {
  return value === true
}

export function normalizeDigestPreferences(response) {
  const raw = response?.notification_prefs || response || {}
  const cadence = cleanCadence(raw.digest_cadence)
  const enabled = isDigestEnabled(raw.digest_enabled) && cadence !== 'off'
  return {
    digest_enabled: enabled,
    digest_cadence: enabled ? cadence : 'off',
  }
}

export function digestPreferencesForEnabled(preferences, enabled) {
  const current = normalizeDigestPreferences(preferences)
  if (!enabled) {
    return {
      digest_enabled: false,
      digest_cadence: 'off',
    }
  }
  return {
    digest_enabled: true,
    digest_cadence: current.digest_cadence === 'off' ? 'daily' : current.digest_cadence,
  }
}

export function digestPreferencesForCadence(preferences, cadence) {
  const nextCadence = cleanCadence(cadence)
  return {
    digest_enabled: nextCadence !== 'off',
    digest_cadence: nextCadence,
  }
}

export async function saveDigestPreferenceSelection({
  draftPreferences,
  savePreferences = updateDigestPreferences,
  setPreferences,
  setStatus,
  setError,
}) {
  const payload = normalizeDigestPreferences(draftPreferences)
  setStatus?.(DIGEST_SAVE_LOADING)
  setError?.(null)
  try {
    const response = await savePreferences(payload)
    const saved = normalizeDigestPreferences(response)
    setPreferences?.(saved)
    setStatus?.(DIGEST_SAVE_SAVED)
    return saved
  } catch (error) {
    setError?.(error)
    setStatus?.(DIGEST_SAVE_ERROR)
    return null
  }
}

function DigestPreferenceRow({ label, children }) {
  return (
    <label className="flex flex-col gap-2 rounded border border-dirt/80 bg-field/45 p-3 sm:flex-row sm:items-center sm:justify-between">
      <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {label}
      </span>
      {children}
    </label>
  )
}

export function DigestPreferencesCardView({
  authLoading = false,
  authenticated = false,
  preferences = null,
  preferencesLoading = false,
  preferencesError = null,
  saveStatus = DIGEST_SAVE_IDLE,
  saveError = null,
  followedTeam = null,
  followedTeamLoading = false,
  onToggleEnabled = () => {},
  onCadenceChange = () => {},
  onSubmit = () => {},
  onRetry = null,
}) {
  const loading = authLoading || preferencesLoading
  const normalized = preferences ? normalizeDigestPreferences(preferences) : null
  const saving = saveStatus === DIGEST_SAVE_LOADING
  const saved = saveStatus === DIGEST_SAVE_SAVED
  const hasSaveError = saveStatus === DIGEST_SAVE_ERROR || Boolean(saveError)
  const teamLabel = followedTeamLoading
    ? 'Loading followed team...'
    : preferredTeamLabel(followedTeam, 'No followed team selected')

  return (
    <section className="mb-6" aria-label="Digest preferences">
      <div className="rounded-lg border border-dirt bg-dugout p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-widest text-chalk300">
              Digest Preferences
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-chalk400">
              Get a bullpen update when BaseballOS sees a meaningful change for your followed team.
            </p>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-chalk500">
              BaseballOS only sends a digest when there is something meaningful to report.
            </p>
          </div>
          <div className="rounded border border-dirt/80 bg-field/45 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Followed team
            </div>
            <div className="mt-1 text-sm text-chalk200">
              {teamLabel}
            </div>
          </div>
        </div>

        {authLoading && (
          <p className="mt-4 font-mono text-xs text-chalk500">Checking sign-in...</p>
        )}

        {!authLoading && !authenticated && (
          <div className="mt-4 rounded border border-dirt/80 bg-field/45 p-3">
            <p className="text-sm leading-relaxed text-chalk400">
              Sign in to manage digest emails for your followed team.
            </p>
            <Link
              to="/signin"
              className="mt-3 inline-flex rounded border border-amber/35 bg-amber/10 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15"
            >
              Sign in
            </Link>
          </div>
        )}

        {authenticated && loading && !normalized && (
          <p className="mt-4 font-mono text-xs text-chalk500">Loading digest preferences...</p>
        )}

        {authenticated && preferencesError && !normalized && (
          <div className="mt-4 rounded border border-red-500/30 bg-red-500/5 p-3" role="alert">
            <p className="text-sm text-red-300">
              Digest preferences are unavailable right now.
            </p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="mt-3 rounded border border-red-400/40 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-red-200"
              >
                Try again
              </button>
            )}
          </div>
        )}

        {authenticated && normalized && (
          <form className="mt-4 space-y-3" onSubmit={onSubmit}>
            <DigestPreferenceRow label="Digest emails">
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-chalk300">
                  {normalized.digest_enabled ? 'On' : 'Off'}
                </span>
                <input
                  type="checkbox"
                  name="digest_enabled"
                  checked={normalized.digest_enabled}
                  disabled={saving}
                  onChange={(event) => onToggleEnabled(event.target.checked)}
                  className="h-4 w-4 accent-amber disabled:cursor-not-allowed disabled:opacity-60"
                />
              </div>
            </DigestPreferenceRow>

            <DigestPreferenceRow label="Cadence">
              <select
                name="digest_cadence"
                value={normalized.digest_cadence}
                disabled={saving}
                onChange={(event) => onCadenceChange(event.target.value)}
                className="rounded border border-dirt bg-field px-3 py-2 font-mono text-xs uppercase tracking-widest text-chalk200 outline-none transition-colors hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="off">Off</option>
              </select>
            </DigestPreferenceRow>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-relaxed text-chalk500">
                Turning this on records your preference. BaseballOS still controls when team digest sends are active.
              </p>
              <button
                type="submit"
                disabled={saving}
                className="rounded border border-amber/35 bg-amber/10 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? 'Saving...' : 'Save preferences'}
              </button>
            </div>

            {saved && (
              <p className="rounded border border-pine/40 bg-pine/10 px-3 py-2 text-sm text-emerald-300">
                Digest preferences saved.
              </p>
            )}
            {hasSaveError && (
              <p className="rounded border border-red-500/30 bg-red-500/5 px-3 py-2 text-sm text-red-300" role="alert">
                We could not save digest preferences. Please try again.
              </p>
            )}
          </form>
        )}
      </div>
    </section>
  )
}

export default function DigestPreferencesCard() {
  const teams = useFetch(getTeams)
  const teamList = teams.data || []
  const {
    preferredTeam,
    loading: followedTeamLoading,
    authLoading,
    authenticated,
  } = usePreferredTeamPreference(teamList)
  const [preferences, setPreferences] = useState(null)
  const [preferencesLoading, setPreferencesLoading] = useState(false)
  const [preferencesError, setPreferencesError] = useState(null)
  const [saveStatus, setSaveStatus] = useState(DIGEST_SAVE_IDLE)
  const [saveError, setSaveError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true

    if (!authenticated) {
      setPreferences(null)
      setPreferencesLoading(false)
      setPreferencesError(null)
      setSaveStatus(DIGEST_SAVE_IDLE)
      setSaveError(null)
      return () => {
        active = false
      }
    }

    setPreferencesLoading(true)
    setPreferencesError(null)
    getDigestPreferences()
      .then((response) => {
        if (!active) return
        setPreferences(normalizeDigestPreferences(response))
      })
      .catch((error) => {
        if (!active) return
        setPreferencesError(error)
      })
      .finally(() => {
        if (active) setPreferencesLoading(false)
      })

    return () => {
      active = false
    }
  }, [authenticated, reloadKey])

  const handleSubmit = async (event) => {
    event.preventDefault()
    await saveDigestPreferenceSelection({
      draftPreferences: preferences,
      setPreferences,
      setStatus: setSaveStatus,
      setError: setSaveError,
    })
  }

  return (
    <DigestPreferencesCardView
      authLoading={authLoading}
      authenticated={authenticated}
      preferences={preferences}
      preferencesLoading={preferencesLoading}
      preferencesError={preferencesError}
      saveStatus={saveStatus}
      saveError={saveError}
      followedTeam={preferredTeam}
      followedTeamLoading={followedTeamLoading || teams.loading}
      onToggleEnabled={(enabled) => {
        setPreferences(current => digestPreferencesForEnabled(current, enabled))
        setSaveStatus(DIGEST_SAVE_IDLE)
      }}
      onCadenceChange={(cadence) => {
        setPreferences(current => digestPreferencesForCadence(current, cadence))
        setSaveStatus(DIGEST_SAVE_IDLE)
      }}
      onSubmit={handleSubmit}
      onRetry={() => setReloadKey(value => value + 1)}
    />
  )
}

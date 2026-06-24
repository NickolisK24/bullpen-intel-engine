import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { usePreferredTeamPreference } from '../../hooks/usePreferredTeamPreference'
import {
  getDigestPreferences,
  getTeams,
  updateDigestPreferences,
} from '../../utils/api'
import {
  normalizePreferredTeam,
  preferredTeamLabel,
  preferredTeamSelectionValue,
} from '../../utils/preferredTeam'

export const DIGEST_SAVE_IDLE = 'idle'
export const DIGEST_SAVE_LOADING = 'loading'
export const DIGEST_SAVE_SAVED = 'saved'
export const DIGEST_SAVE_ERROR = 'error'

export const FOLLOWED_TEAM_SAVE_IDLE = 'idle'
export const FOLLOWED_TEAM_SAVE_LOADING = 'loading'
export const FOLLOWED_TEAM_SAVE_SAVED = 'saved'
export const FOLLOWED_TEAM_SAVE_ERROR = 'error'

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

export function followedTeamOptionFromDirectoryTeam(team) {
  const normalized = normalizePreferredTeam(team)
  if (!normalized) return null

  const label = preferredTeamLabel(normalized, null)
  const value = preferredTeamSelectionValue(normalized)
  if (!label || !value) return null

  return {
    value,
    label,
    abbreviation: normalized.team_abbreviation || '',
    team: normalized,
  }
}

export function buildFollowedTeamOptions(teams = []) {
  const seen = new Set()
  const options = []

  for (const team of (Array.isArray(teams) ? teams : [])) {
    const option = followedTeamOptionFromDirectoryTeam(team)
    if (!option) continue
    const keys = [
      option.value,
      option.abbreviation ? `abbr:${option.abbreviation.toLowerCase()}` : null,
      option.label ? `name:${option.label.toLowerCase()}` : null,
    ].filter(Boolean)
    if (keys.some(key => seen.has(key))) continue
    keys.forEach(key => seen.add(key))
    options.push(option)
  }

  return options.sort((left, right) => (
    left.label.localeCompare(right.label)
    || left.abbreviation.localeCompare(right.abbreviation)
  ))
}

export function filterFollowedTeamOptions(options = [], query = '') {
  const needle = String(query || '').trim().toLowerCase()
  const safeOptions = Array.isArray(options) ? options : []
  if (!needle) return safeOptions
  return safeOptions.filter(option => (
    option.label.toLowerCase().includes(needle)
    || option.abbreviation.toLowerCase().includes(needle)
  ))
}

export async function saveFollowedTeamSelection({
  selectedValue,
  options = [],
  setPreferredTeam,
  setFollowedTeam,
  setStatus,
  setError,
}) {
  const option = (Array.isArray(options) ? options : []).find(item => item.value === selectedValue)
  if (!option || typeof setPreferredTeam !== 'function') return null

  setStatus?.(FOLLOWED_TEAM_SAVE_LOADING)
  setError?.(null)
  try {
    const saved = await Promise.resolve(setPreferredTeam(option.team))
    const followedTeam = normalizePreferredTeam(saved) || option.team
    setFollowedTeam?.(followedTeam)
    setStatus?.(FOLLOWED_TEAM_SAVE_SAVED)
    return followedTeam
  } catch (error) {
    setError?.(error)
    setStatus?.(FOLLOWED_TEAM_SAVE_ERROR)
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

export function FollowedTeamPickerView({
  options = [],
  query = '',
  selectedValue = '',
  currentValue = '',
  loading = false,
  error = null,
  saving = false,
  saveError = null,
  onQueryChange = () => {},
  onSelectTeam = () => {},
  onSave = () => {},
  onCancel = () => {},
}) {
  const filteredOptions = filterFollowedTeamOptions(options, query)

  return (
    <div className="mt-3 rounded border border-dirt/80 bg-field/45 p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <label className="flex min-w-0 flex-1 flex-col gap-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Search teams
          <input
            type="search"
            value={query}
            disabled={loading || saving}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Team name"
            className="rounded border border-dirt bg-dugout px-3 py-2 text-sm normal-case tracking-normal text-chalk200 outline-none transition-colors placeholder:text-chalk600 hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
          />
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded border border-dirt px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-chalk400 transition-colors hover:border-chalk400 hover:text-chalk200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving || loading || !selectedValue}
            className="rounded border border-amber/35 bg-amber/10 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving...' : 'Save team'}
          </button>
        </div>
      </div>

      {loading && (
        <p className="mt-3 font-mono text-xs text-chalk500">Loading teams...</p>
      )}
      {error && (
        <p className="mt-3 rounded border border-red-500/30 bg-red-500/5 px-3 py-2 text-sm text-red-300" role="alert">
          Team list is unavailable right now.
        </p>
      )}
      {saveError && (
        <p className="mt-3 rounded border border-red-500/30 bg-red-500/5 px-3 py-2 text-sm text-red-300" role="alert">
          We could not save your followed team. Please try again.
        </p>
      )}

      {!loading && !error && (
        <div className="mt-3 max-h-72 overflow-y-auto rounded border border-dirt/70 bg-dugout/75" role="listbox" aria-label="Choose followed team">
          {filteredOptions.length > 0 ? filteredOptions.map(option => {
            const selected = option.value === selectedValue
            const current = option.value === currentValue
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => onSelectTeam(option.value)}
                className={`flex w-full items-center justify-between gap-3 border-b border-dirt/60 px-3 py-2 text-left text-sm transition-colors last:border-b-0 ${
                  selected
                    ? 'bg-amber/10 text-chalk100'
                    : 'text-chalk300 hover:bg-field/60 hover:text-chalk100'
                }`}
              >
                <span className="min-w-0 break-words">{option.label}</span>
                {current && (
                  <span className="shrink-0 rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest text-emerald-300">
                    Current
                  </span>
                )}
              </button>
            )
          }) : (
            <p className="px-3 py-3 text-sm text-chalk500">No teams match that search.</p>
          )}
        </div>
      )}
    </div>
  )
}

function FollowedTeamPreferenceBlock({
  followedTeam = null,
  followedTeamLoading = false,
  teams = [],
  teamsLoading = false,
  teamsError = null,
  pickerOpen = false,
  query = '',
  selectedValue = '',
  saveStatus = FOLLOWED_TEAM_SAVE_IDLE,
  saveError = null,
  serverSyncLoading = false,
  serverSyncError = null,
  onOpenPicker = () => {},
  onCancelPicker = () => {},
  onQueryChange = () => {},
  onSelectTeam = () => {},
  onSaveTeam = () => {},
}) {
  const teamLabel = followedTeamLoading
    ? 'Loading followed team...'
    : preferredTeamLabel(followedTeam, 'No followed team selected')
  const options = buildFollowedTeamOptions(teams)
  const currentValue = preferredTeamSelectionValue(followedTeam)
  const saving = saveStatus === FOLLOWED_TEAM_SAVE_LOADING || serverSyncLoading
  const saved = saveStatus === FOLLOWED_TEAM_SAVE_SAVED
  const hasSaveError = saveStatus === FOLLOWED_TEAM_SAVE_ERROR || Boolean(saveError)

  return (
    <div className="mt-4 rounded border border-dirt/80 bg-field/45 p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Followed Team
          </div>
          <div className="mt-1 text-sm text-chalk100">
            {teamLabel}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-chalk500">
            Your digest follows this team.
          </p>
        </div>
        {!pickerOpen && (
          <button
            type="button"
            onClick={onOpenPicker}
            disabled={followedTeamLoading || teamsLoading || saving}
            className="rounded border border-amber/35 bg-amber/10 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Switch Team
          </button>
        )}
      </div>

      {serverSyncError && !hasSaveError && (
        <p className="mt-3 rounded border border-red-500/30 bg-red-500/5 px-3 py-2 text-sm text-red-300" role="alert">
          Followed team sync is unavailable right now.
        </p>
      )}

      {saved && !pickerOpen && (
        <p className="mt-3 rounded border border-pine/40 bg-pine/10 px-3 py-2 text-sm text-emerald-300">
          Followed team saved.
        </p>
      )}

      {pickerOpen && (
        <FollowedTeamPickerView
          options={options}
          query={query}
          selectedValue={selectedValue || currentValue}
          currentValue={currentValue}
          loading={teamsLoading}
          error={teamsError}
          saving={saving}
          saveError={hasSaveError ? saveError || serverSyncError : null}
          onQueryChange={onQueryChange}
          onSelectTeam={onSelectTeam}
          onSave={onSaveTeam}
          onCancel={onCancelPicker}
        />
      )}
    </div>
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
  teams = [],
  teamsLoading = false,
  teamsError = null,
  focused = false,
  teamPickerOpen = false,
  teamPickerQuery = '',
  selectedTeamValue = '',
  followedTeamSaveStatus = FOLLOWED_TEAM_SAVE_IDLE,
  followedTeamSaveError = null,
  serverSyncLoading = false,
  serverSyncError = null,
  onToggleEnabled = () => {},
  onCadenceChange = () => {},
  onSubmit = () => {},
  onRetry = null,
  onOpenTeamPicker = () => {},
  onCancelTeamPicker = () => {},
  onTeamPickerQueryChange = () => {},
  onSelectTeamValue = () => {},
  onSaveFollowedTeam = () => {},
}) {
  const loading = authLoading || preferencesLoading
  const normalized = preferences ? normalizeDigestPreferences(preferences) : null
  const saving = saveStatus === DIGEST_SAVE_LOADING
  const saved = saveStatus === DIGEST_SAVE_SAVED
  const hasSaveError = saveStatus === DIGEST_SAVE_ERROR || Boolean(saveError)

  return (
    <section
      id="digest-preferences"
      className={`mb-6 scroll-mt-20 transition-shadow ${focused ? 'rounded-lg shadow-[0_0_0_2px_rgba(230,167,75,0.45)]' : ''}`}
      aria-label="Digest preferences"
      tabIndex={focused ? -1 : undefined}
    >
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

        {authenticated && (
          <FollowedTeamPreferenceBlock
            followedTeam={followedTeam}
            followedTeamLoading={followedTeamLoading}
            teams={teams}
            teamsLoading={teamsLoading}
            teamsError={teamsError}
            pickerOpen={teamPickerOpen}
            query={teamPickerQuery}
            selectedValue={selectedTeamValue}
            saveStatus={followedTeamSaveStatus}
            saveError={followedTeamSaveError}
            serverSyncLoading={serverSyncLoading}
            serverSyncError={serverSyncError}
            onOpenPicker={onOpenTeamPicker}
            onCancelPicker={onCancelTeamPicker}
            onQueryChange={onTeamPickerQueryChange}
            onSelectTeam={onSelectTeamValue}
            onSaveTeam={onSaveFollowedTeam}
          />
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

export default function DigestPreferencesCard({ focused = false } = {}) {
  const teams = useFetch(getTeams)
  const teamList = teams.data || []
  const {
    preferredTeam,
    loading: followedTeamLoading,
    authLoading,
    authenticated,
    setPreferredTeam,
    serverSyncLoading,
    serverSyncError,
  } = usePreferredTeamPreference(teamList)
  const [preferences, setPreferences] = useState(null)
  const [preferencesLoading, setPreferencesLoading] = useState(false)
  const [preferencesError, setPreferencesError] = useState(null)
  const [saveStatus, setSaveStatus] = useState(DIGEST_SAVE_IDLE)
  const [saveError, setSaveError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [displayFollowedTeam, setDisplayFollowedTeam] = useState(preferredTeam)
  const [teamPickerOpen, setTeamPickerOpen] = useState(false)
  const [teamPickerQuery, setTeamPickerQuery] = useState('')
  const [selectedTeamValue, setSelectedTeamValue] = useState('')
  const [followedTeamSaveStatus, setFollowedTeamSaveStatus] = useState(FOLLOWED_TEAM_SAVE_IDLE)
  const [followedTeamSaveError, setFollowedTeamSaveError] = useState(null)
  const followedTeamOptions = useMemo(() => buildFollowedTeamOptions(teamList), [teamList])

  useEffect(() => {
    setDisplayFollowedTeam(preferredTeam)
  }, [preferredTeam])

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

  const handleOpenTeamPicker = () => {
    setTeamPickerOpen(true)
    setTeamPickerQuery('')
    setSelectedTeamValue(preferredTeamSelectionValue(displayFollowedTeam))
    setFollowedTeamSaveStatus(FOLLOWED_TEAM_SAVE_IDLE)
    setFollowedTeamSaveError(null)
  }

  const handleCancelTeamPicker = () => {
    setTeamPickerOpen(false)
    setTeamPickerQuery('')
    setSelectedTeamValue('')
    setFollowedTeamSaveStatus(FOLLOWED_TEAM_SAVE_IDLE)
    setFollowedTeamSaveError(null)
  }

  const handleSaveFollowedTeam = async () => {
    const saved = await saveFollowedTeamSelection({
      selectedValue: selectedTeamValue,
      options: followedTeamOptions,
      setPreferredTeam,
      setFollowedTeam: setDisplayFollowedTeam,
      setStatus: setFollowedTeamSaveStatus,
      setError: setFollowedTeamSaveError,
    })
    if (saved) {
      setSelectedTeamValue(preferredTeamSelectionValue(saved))
      setTeamPickerOpen(false)
      setTeamPickerQuery('')
    }
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
      followedTeam={displayFollowedTeam}
      followedTeamLoading={followedTeamLoading || teams.loading}
      teams={teamList}
      teamsLoading={teams.loading}
      teamsError={teams.error}
      focused={focused}
      teamPickerOpen={teamPickerOpen}
      teamPickerQuery={teamPickerQuery}
      selectedTeamValue={selectedTeamValue}
      followedTeamSaveStatus={followedTeamSaveStatus}
      followedTeamSaveError={followedTeamSaveError}
      serverSyncLoading={serverSyncLoading}
      serverSyncError={serverSyncError}
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
      onOpenTeamPicker={handleOpenTeamPicker}
      onCancelTeamPicker={handleCancelTeamPicker}
      onTeamPickerQueryChange={(query) => setTeamPickerQuery(query)}
      onSelectTeamValue={(value) => {
        setSelectedTeamValue(value)
        setFollowedTeamSaveStatus(FOLLOWED_TEAM_SAVE_IDLE)
        setFollowedTeamSaveError(null)
      }}
      onSaveFollowedTeam={handleSaveFollowedTeam}
    />
  )
}

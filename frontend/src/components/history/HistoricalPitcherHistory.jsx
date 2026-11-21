import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getHistoricalPitcherDecisions } from '../../utils/api'
import { buildRehearsalPitcherHref, matchesDecisionPage } from '../../utils/evidenceLinks'
import { ErrorState, LoadingPane } from '../UI'

const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const cited = source => digest(source?.facts_digest) && digest(source?.input_digest)

export function matchesPitcherDecisions(page, edition, revision) {
  if (!matchesDecisionPage(page, revision) || page.scope !== 'isolated_historical_pitcher_history'
      || page.public_pitcher_id !== edition.public_pitcher_id
      || (revision === edition.selection_revision && page.rows[0].generation !== edition.generation)) return false
  return page.rows.every(row => {
    if (!['select', 'rollback'].includes(row.action)) return false
    if (row.generation === null) return row.action === 'rollback' && row.status === 'no_selected_generation' && !row.identity
    if (!digest(row.generation) || !/^\d{4}-\d{2}-\d{2}$/.test(row.represented)) return false
    if (!row.identity) return row.status !== 'represented' && row.arm == null && row.role == null
    if (!['represented', 'historical_roster_departure', 'dated_roster_identity', 'dated_active_pitcher'].includes(row.status)) return false
    return row.identity.public_id === edition.public_pitcher_id && row.identity.mlb_id === edition.pitcher.mlb_id
  })
}

export function PitcherDecisionRows({ rows, pitcherId }) {
  return <ol>{rows.map(row => {
    const href = row.identity && buildRehearsalPitcherHref(pitcherId, row.selection_revision, row.generation)
    const heading = `Revision ${row.selection_revision}${row.represented ? ' · ' + row.represented : ''}`
    const role = row.role
    const read = row.arm?.read
    const pattern = row.status === 'represented' && !role?.reason && role?.through === row.represented
      && cited(row.citations?.candidate_pitcher_profile_v1) && role.role?.role
    const label = row.status === 'represented' && read?.arm_read?.kind === 'read'
      && row.availability_reference && read.availability?.inputs?.reference_date === row.availability_reference
      && cited(row.citations?.candidate_regular_readiness_v1) && read.arm_read.label
    return <li key={row.selection_revision} className="border-t border-dirt py-2">
      {href ? <Link className="underline" to={href}>{heading}</Link> : heading}
      {row.team_abbreviation && ` · ${row.team_abbreviation}`}{row.action === 'rollback' && ' · Rollback'}
      {row.generation === null ? <p>No edition selected.</p> : <>
        <p>Observed usage pattern · {pattern || 'Unavailable'}</p>
        <p>{label ? `Arm read for ${row.availability_reference} · ${label}` : 'Dated arm read unavailable.'}</p>
      </>}
    </li>
  })}</ol>
}

function DecisionPage({ edition, revision }) {
  const id = edition.public_pitcher_id
  const [earlier, setEarlier] = useState(false)
  const read = useFetch(options => getHistoricalPitcherDecisions(id, revision, options), [id, revision])
  if (read.loading) return <LoadingPane message="Loading pitcher editions…" />
  if (read.error || !matchesPitcherDecisions(read.data, edition, revision)) {
    return <ErrorState message={read.error || 'Pitcher edition history could not be verified.'} onRetry={read.refetch} />
  }
  return <>
    <PitcherDecisionRows rows={read.data.rows} pitcherId={id} />
    {read.data.next_revision && (earlier
      ? <DecisionPage edition={edition} revision={read.data.next_revision} />
      : <button type="button" className="underline" onClick={() => setEarlier(true)}>Show earlier editions</button>)}
  </>
}

export default function HistoricalPitcherHistory({ edition }) {
  const [open, setOpen] = useState(false)
  return <section className="border-t border-dirt p-4 sm:p-5">
    <h2 className="font-display text-lg text-chalk100">Historical workload reads and usage patterns</h2>
    {open ? <DecisionPage edition={edition} revision={edition.selection_revision} />
      : <button type="button" className="underline" onClick={() => setOpen(true)}>View pitcher editions</button>}
  </section>
}

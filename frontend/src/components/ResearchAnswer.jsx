import { useState, useSyncExternalStore } from 'react'
import { PUBLIC_TEAM_STATE_LABELS } from '../adapters/publicTeamState'
import { currentResearchVisit, subscribeResearchVisit, submitResearchAnswer } from '../utils/trafficMeasurement'

const noVisit = () => null

function useVisit(surface) {
  const visit = useSyncExternalStore(subscribeResearchVisit, currentResearchVisit, noVisit)
  return visit?.surface === surface ? visit : null
}

const choice = 'min-h-11 rounded border border-line-default px-3 text-sm'

export function SearchAnswer() {
  const visit = useVisit('search')
  if (!visit) return null
  if (visit.answered) return <p role="status">Thanks for your feedback.</p>
  return <fieldset className="mt-4 flex gap-2">
    <legend className="mb-1 text-sm">Did these results answer your question?</legend>
    <button type="button" className={choice} onClick={() => submitResearchAnswer(visit, 'answered')}>Yes</button>
    <button type="button" className={choice} onClick={() => submitResearchAnswer(visit, 'unanswered_question')}>No</button>
  </fieldset>
}

function normalizeName(name) {
  return name.trim().toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').replace(/\s+/g, ' ')
}

function BoardCheck({ visit, label, names }) {
  const [arm, setArm] = useState('')
  const [state, setState] = useState('')
  if (visit.answered) return <p role="status">Thanks for taking the Board check.</p>
  return <details className="mt-3 text-sm">
    <summary className="cursor-pointer">Check your Board read</summary>
    <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={event => {
      event.preventDefault()
      const correct = state === label && names.some(name => normalizeName(name) === normalizeName(arm))
      submitResearchAnswer(visit, correct ? 'correct' : 'incorrect')
    }}>
      <label>Published Team State <select required className={choice} value={state} onChange={e => setState(e.target.value)}>
        <option value="">Select state</option>
        {PUBLIC_TEAM_STATE_LABELS.map(value => <option key={value}>{value}</option>)}
      </select></label>
      <label>Name one active bullpen arm <input required maxLength={100} autoComplete="off" className={choice}
        value={arm} onChange={e => setArm(e.target.value)} /></label>
      <button className={choice} type="submit">Submit answer</button>
    </form>
  </details>
}

export function BoardAnswer({ view, read }) {
  const visit = useVisit('bullpen_board')
  if (!visit || !view.teamState.available || view.isStale || view.isSample ||
      read?.sectionStatus?.active_bullpen?.status !== 'available') return null
  if (visit.team && ![String(read?.team?.team_id), view.teamAbbreviation].includes(visit.team)) return null
  const names = (read?.activeBullpen?.arms || []).filter(arm => arm.pitcher_id && arm.name).map(arm => arm.name)
  return names.length ? <BoardCheck key={visit.id} visit={visit} label={view.teamState.publicLabel} names={names} /> : null
}

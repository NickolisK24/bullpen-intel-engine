import { Navigate, useLocation } from 'react-router-dom'
import {
  BULLPEN_VIEWS,
  buildPitcherHref,
  readBullpenLocation,
  parseRehearsalRevision,
} from '../../utils/evidenceLinks'
import Bullpen from './Bullpen'
import HistoricalTeamBoard from './board/HistoricalTeamBoard'
import { ErrorState } from '../UI'

export function legacyPitcherDestination(search = '', hash = '') {
  const state = readBullpenLocation(search, hash)
  if (state.view !== BULLPEN_VIEWS.BOARD || state.pitcherId == null) return null
  return buildPitcherHref(state.pitcherId)
}

export default function BullpenRoute() {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  if (params.has('rehearsalRevision') || params.has('rehearsalGeneration')) {
    const teamParam = params.get('team')
    const team = Number(teamParam)
    const generation = params.get('rehearsalGeneration')
    let revision
    try {
      revision = parseRehearsalRevision(params.get('rehearsalRevision'), params.getAll('rehearsalRevision').length > 1)
      if (!revision || !/^[a-f0-9]{64}$/.test(generation) || params.getAll('rehearsalGeneration').length !== 1
        || !/^[1-9]\d*$/.test(teamParam) || !Number.isSafeInteger(team) || params.getAll('team').length !== 1
        || params.get('view') !== 'board' || params.getAll('view').length !== 1 || params.has('pitcher')) {
        throw new Error('Invalid historical Team Board destination.')
      }
    } catch (error) {
      return <ErrorState message={error.message} />
    }
    return <HistoricalTeamBoard key={location.search} team={team} revision={revision} generation={generation} />
  }
  const destination = legacyPitcherDestination(location.search, location.hash)

  return destination
    ? <Navigate to={destination} replace />
    : <Bullpen />
}

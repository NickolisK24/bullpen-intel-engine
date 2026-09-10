import { Navigate, useLocation } from 'react-router-dom'
import {
  BULLPEN_VIEWS,
  buildPitcherHref,
  readBullpenLocation,
} from '../../utils/evidenceLinks'
import Bullpen from './Bullpen'

export function legacyPitcherDestination(search = '', hash = '') {
  const state = readBullpenLocation(search, hash)
  if (state.view !== BULLPEN_VIEWS.BOARD || state.pitcherId == null) return null
  return buildPitcherHref(state.pitcherId)
}

export default function BullpenRoute() {
  const location = useLocation()
  const destination = legacyPitcherDestination(location.search, location.hash)

  return destination
    ? <Navigate to={destination} replace />
    : <Bullpen />
}

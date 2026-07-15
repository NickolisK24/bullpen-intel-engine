import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { observeTrafficRoute } from '../utils/trafficMeasurement'

export default function TrafficRouteObserver() {
  const location = useLocation()

  useEffect(() => {
    try {
      observeTrafficRoute({
        locationKey: location.key,
        hostname: window.location.hostname,
        pathname: location.pathname,
        search: location.search,
        hash: location.hash,
        referrer: document.referrer,
        storage: window.localStorage,
      })
    } catch {
      // Measurement is intentionally invisible and isolated from navigation.
    }
  }, [location.key, location.pathname, location.search, location.hash])

  return null
}

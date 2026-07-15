import { readAuthToken } from './api'

export const TRAFFIC_REPORTING_PATH = '/admin/product-intelligence'
export const TRAFFIC_REPORTING_RANGES = Object.freeze(['7d', '30d', '90d', 'all'])

function reportingUrl(range, configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL) {
  const apiBase = configuredBackendOrigin ? `${configuredBackendOrigin}/api` : '/api'
  return `${apiBase}/traffic/internal/summary?range=${encodeURIComponent(range)}`
}

export async function fetchTrafficSummary(range = '7d', {
  fetchImpl = globalThis.fetch,
  authToken = readAuthToken(),
  configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL,
} = {}) {
  const selectedRange = TRAFFIC_REPORTING_RANGES.includes(range) ? range : '7d'
  const headers = { 'Content-Type': 'application/json' }
  if (authToken) headers.Authorization = `Bearer ${authToken}`

  const response = await fetchImpl(reportingUrl(selectedRange, configuredBackendOrigin), {
    method: 'GET',
    headers,
  })
  if (!response.ok) {
    const error = new Error(`Traffic reporting request failed with ${response.status}`)
    error.status = response.status
    throw error
  }
  return response.json()
}

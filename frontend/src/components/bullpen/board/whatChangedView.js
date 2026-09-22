import { formatDateOnly } from '../../../utils/dateDisplay'

const domainLabels = {
  team_state: 'Team State',
  roster: 'Active bullpen',
  workload_rest: 'Workload and rest',
  transactions: 'Roster transaction',
  rotation: 'Rotation impact',
}

const handoffTargets = {
  team_state: { href: '#team-board-answer', label: 'Review Team State' },
  roster: { href: '#active-bullpen', label: 'Review active bullpen' },
  workload_rest: { href: '#recent-usage', label: 'Review recent usage' },
  transactions: { href: '#roster-transactions', label: 'Review roster changes' },
  rotation: { href: '#rotation-impact', label: 'Review rotation impact' },
}

export function getWhatChangedView(payload) {
  const source = payload && typeof payload === 'object' ? payload : null
  if (!source) {
    return {
      valid: false, state: 'unavailable', comparisonStatus: 'unavailable',
      previousDate: null, previousDateLabel: null, currentDate: null,
      currentDateLabel: null, quietMessage: null, events: [], unavailableDomains: [],
    }
  }

  const unavailableDomains = Object.entries(source.domains || {})
    .filter(([, domain]) => domain?.status !== 'complete')
    .map(([key, domain]) => ({
      key,
      label: domainLabels[key] || key.replaceAll('_', ' '),
      status: domain?.status || 'unavailable',
    }))

  return {
    valid: true,
    state: source.state,
    comparisonStatus: source.comparisonStatus,
    previousDate: source.previousRepresentedDate,
    previousDateLabel: formatDateOnly(source.previousRepresentedDate, { month: 'short' }),
    currentDate: source.currentRepresentedDate,
    currentDateLabel: formatDateOnly(source.currentRepresentedDate, { month: 'short' }),
    quietMessage: source.quietMessage,
    teamStateOutcome: source.domains?.team_state?.outcome || null,
    events: (source.events || []).map(event => ({
      ...event,
      domainLabel: domainLabels[event.domain] || event.domain,
      handoff: handoffTargets[event.domain] || null,
      eventDateLabel: formatDateOnly(event.eventDate, { month: 'short' }),
      subject: event.facts?.pitcher_name || null,
    })),
    unavailableDomains,
  }
}

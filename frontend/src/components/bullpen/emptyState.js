export function getBullpenEmptyState({
  allRowsCount = 0,
  visibleRowsCount = 0,
  meta = null,
  includeStale = false,
  selectedTeam = null,
  selectedTeamLabel = null,
  riskFilter = 'ALL',
  availabilityFilter = 'ALL',
  searchTerm = '',
} = {}) {
  if (visibleRowsCount > 0) return null

  const query = searchTerm.trim()
  const totalLogs = meta?.total_game_logs ?? 0
  const totalScored = meta?.total_scored_pitchers ?? 0
  const filteredScored = meta?.filtered_scored_pitchers ?? 0
  const staleFiltered = meta?.stale_filtered_pitchers ?? 0
  const hasWorkloadData = totalLogs > 0 || totalScored > 0 || filteredScored > 0 || allRowsCount > 0

  if (!hasWorkloadData) {
    return {
      title: 'No pitcher workload data found',
      subtitle: 'No pitcher workload data is loaded for this view.',
    }
  }

  if (totalLogs > 0 && totalScored === 0) {
    return {
      title: 'No recent workload reads found',
      subtitle: 'Game logs are present, but recent workload reads have not been calculated yet.',
    }
  }

  if (!includeStale && allRowsCount === 0 && staleFiltered > 0) {
    return {
      title: 'No current pitchers match the freshness filter.',
      subtitle: 'Enable "Show pitchers outside the freshness window" to view tracked pitchers with stale workload reads.',
    }
  }

  if (query) {
    return {
      title: 'No pitchers match your search.',
      subtitle: 'Clear the search or adjust the team, availability, risk, or freshness filters.',
    }
  }

  if (availabilityFilter && availabilityFilter !== 'ALL') {
    return {
      title: `No pitchers match the ${availabilityFilter} availability filter.`,
      subtitle: 'Adjust the availability status, team, risk, or freshness setting to expand the list.',
    }
  }

  if (riskFilter && riskFilter !== 'ALL') {
    return {
      title: `No ${riskFilter.toLowerCase()} risk pitchers match the current filters.`,
      subtitle: 'Adjust the risk tier, team, or freshness setting to expand the list.',
    }
  }

  if (selectedTeam) {
    return {
      title: `No pitchers match ${selectedTeamLabel || 'the selected team'}.`,
      subtitle: 'Choose another team or adjust the freshness setting.',
    }
  }

  return {
    title: 'No pitchers match the current filters.',
    subtitle: 'Adjust the team, availability, risk, search, or freshness controls.',
  }
}

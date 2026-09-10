const EASTERN_TIME_ZONE = 'America/New_York'
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

function partsObject(formatter, date) {
  return Object.fromEntries(
    formatter.formatToParts(date)
      .filter(part => part.type !== 'literal')
      .map(part => [part.type, part.value]),
  )
}

export function formatAdminDateTime(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw) return { display: '—', title: null }

  if (DATE_ONLY.test(raw)) {
    const date = new Date(`${raw}T00:00:00Z`)
    if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== raw) {
      return { display: '—', title: null }
    }
    return {
      display: new Intl.DateTimeFormat('en-US', {
        month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC',
      }).format(date),
      title: raw,
    }
  }

  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return { display: '—', title: null }
  const parts = partsObject(new Intl.DateTimeFormat('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: EASTERN_TIME_ZONE,
  }), date)
  return {
    display: `${parts.month} ${parts.day}, ${parts.year} at ${parts.hour}:${parts.minute} ${parts.dayPeriod} ET`,
    title: raw,
  }
}

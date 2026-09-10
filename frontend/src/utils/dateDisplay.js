const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November', 'December']

const ET_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'America/New_York',
})

const ET_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'America/New_York',
})

const ISO_DATE_TIME_WITHOUT_ZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/

function parseUtcDateTime(value) {
  if (!value) return null
  if (value instanceof Date) return value

  const raw = String(value).trim()
  if (!raw) return null

  // Backend UTC timestamps are sometimes stored as timezone-less ISO strings.
  // Treat that exact shape as UTC before rendering an ET label.
  const normalized = ISO_DATE_TIME_WITHOUT_ZONE.test(raw) ? `${raw}Z` : raw
  return new Date(normalized)
}

export function formatUtcDateTimeEt(value, { includeDate = true } = {}) {
  const date = parseUtcDateTime(value)
  if (!date) return null
  if (Number.isNaN(date.getTime())) return null
  const formatter = includeDate ? ET_DATE_TIME_FORMATTER : ET_TIME_FORMATTER
  return `${formatter.format(date)} ET`
}

export function formatDateOnly(value, { month = 'long' } = {}) {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value))
  if (!match) return null
  const [, year, monthValue, dayValue] = match
  const monthIndex = Number(monthValue) - 1
  const day = Number(dayValue)
  if (monthIndex < 0 || monthIndex > 11 || day < 1 || day > 31) return null
  const monthName = month === 'short' ? MONTHS_SHORT[monthIndex] : MONTHS_LONG[monthIndex]
  return `${monthName} ${day}, ${year}`
}

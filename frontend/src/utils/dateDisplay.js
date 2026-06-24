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

export function formatUtcDateTimeEt(value, { includeDate = true } = {}) {
  if (!value) return null
  const date = new Date(value)
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

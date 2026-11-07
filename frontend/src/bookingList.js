export const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export const time = new Intl.DateTimeFormat('en-US', {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'America/Chicago',
  timeZoneName: 'short',
})

// Turns an API value such as "coolant_leak" into "Coolant leak".
export function humanize(value) {
  if (!value) return '—'
  const words = value.replaceAll('_', ' ')
  return words[0].toUpperCase() + words.slice(1)
}

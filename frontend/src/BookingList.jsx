import { useEffect, useState } from 'react'
import { humanize, money, time } from './bookingList.js'

async function requestJson(path, options) {
  const res = await fetch(path, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    throw new Error(
      typeof body?.detail === 'string' ? body.detail : `Request failed with status ${res.status}`,
    )
  }
  return body
}

// Reloads whenever `refreshKey` changes, so a new booking appears without reloading the page.
function BookingList({ refreshKey }) {
  const [bookings, setBookings] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [loadAttempt, setLoadAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    requestJson('/api/voice/bookings', { signal: controller.signal })
      .then((loaded) => {
        setBookings(loaded)
        setLoadError(null)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setLoadError(err.message)
      })
    return () => controller.abort()
  }, [loadAttempt, refreshKey])

  return (
    <section aria-label="Booked repairs">
      <h2>Booked repairs</h2>

      {loadError && (
        <div role="alert">
          <p>Couldn't load booked repairs: {loadError}</p>
          <button
            type="button"
            onClick={() => {
              setLoadError(null)
              setLoadAttempt((n) => n + 1)
            }}
          >
            Try again
          </button>
        </div>
      )}
      {!loadError && bookings === null && <p role="status">Loading booked repairs…</p>}
      {bookings?.length === 0 && <p>No repairs booked yet.</p>}

      {bookings?.length > 0 && (
        <div className="issue-table">
          <table>
            <thead>
              <tr>
                <th scope="col">Booking</th>
                <th scope="col">Truck</th>
                <th scope="col">Problem</th>
                <th scope="col">Location</th>
                <th scope="col">Shop</th>
                <th scope="col">Estimate</th>
                <th scope="col">Start time</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((booking) => (
                <tr key={booking.bookingId}>
                  <td>
                    <code>{booking.bookingId}</code>
                  </td>
                  <td>{booking.truckUnitNumber}</td>
                  <td>{humanize(booking.problem)}</td>
                  <td>{booking.location ?? '—'}</td>
                  <td>{booking.shopName}</td>
                  <td>{money.format(booking.estimate)}</td>
                  <td>{time.format(new Date(booking.startTime))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default BookingList

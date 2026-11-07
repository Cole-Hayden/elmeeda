import { money, time } from './bookingList.js'
import FailureSwitch from './FailureSwitch.jsx'

const FAILURE_TEXT = {
  shop_timeout: "didn't respond",
  shop_error: 'returned an error',
}

function BookingDetails({ details }) {
  return (
    <dl>
      {details.bookingId && (
        <>
          <dt>Booking ID</dt>
          <dd>{details.bookingId}</dd>
        </>
      )}
      <dt>Shop</dt>
      <dd>{details.shopName}</dd>
      <dt>Estimate</dt>
      <dd>{money.format(details.estimate)}</dd>
      <dt>Start time</dt>
      <dd>{time.format(new Date(details.startTime))}</dd>
    </dl>
  )
}

function VoiceCall({ call }) {
  const { status, error, issueId, missing, search, prepared, booking, start, stop } = call
  const inCall = status !== 'idle'

  return (
    <section aria-label="Voice call">
      <h2>Voice call</h2>
      <button type="button" onClick={inCall ? stop : start}>
        {inCall ? 'End call' : 'Start call'}
      </button>
      <p role="status">
        {status === 'connecting' && 'Connecting…'}
        {status === 'live' && 'Listening. Go ahead and speak.'}
      </p>
      {error && <p role="alert">{error}</p>}
      {issueId && <p>Issue {issueId}</p>}

      {missing.length > 0 && !search && <p>Still needed: {missing.join(', ')}</p>}

      {search && !booking && (
        <section aria-label="Shop options">
          <h3>Shops</h3>
          <ul>
            {search.options.map((option) => (
              <li key={option.shopId}>
                {option.name}: {money.format(option.estimate)}, {option.distanceMiles} mi, starts{' '}
                {time.format(new Date(option.earliestStart))}, {option.openBays} open bays
              </li>
            ))}
            {search.excluded.map((shop) => (
              <li key={shop.shopId}>
                <s>{shop.name}</s>: {shop.reason.replaceAll('_', ' ')}
              </li>
            ))}
            {search.unavailable.map((shop) => (
              <li key={shop.shopId}>
                <s>{shop.name}</s>: {FAILURE_TEXT[shop.reason]}
              </li>
            ))}
          </ul>
        </section>
      )}

      {prepared && !booking && (
        <section aria-label="Waiting for confirmation">
          <h3>Waiting for your yes. Nothing is booked yet.</h3>
          <BookingDetails details={prepared} />
        </section>
      )}

      {booking && (
        <section role="status" aria-label="Booking confirmed">
          <h3>{booking.alreadyBooked ? 'Already booked. No new booking was made.' : 'Booked'}</h3>
          <BookingDetails details={booking} />
        </section>
      )}

      <FailureSwitch refreshKey={booking?.bookingId} />
    </section>
  )
}

export default VoiceCall

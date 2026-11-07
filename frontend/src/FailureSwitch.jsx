import { useEffect, useState } from 'react'

const FAULTS = [
  { value: 'none', label: 'Working normally' },
  { value: 'timeout', label: 'Time out' },
  { value: 'error', label: 'Return an error' },
  { value: 'no_open_bay', label: 'No open bay' },
]

// Reloads whenever `refreshKey` changes, so open bays stay current after a booking.
function FailureSwitch({ refreshKey }) {
  const [shops, setShops] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/voice/shops', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
        return res.json()
      })
      .then((loaded) => {
        setShops(loaded)
        setError(null)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
    return () => controller.abort()
  }, [refreshKey])

  async function setFault(shopId, fault) {
    setError(null)
    try {
      const res = await fetch(`/api/voice/shops/${shopId}/fault`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fault }),
      })
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const updated = await res.json()
      setShops((current) =>
        current.map((shop) => (shop.shopId === updated.shopId ? updated : shop)),
      )
    } catch (err) {
      setError(`Couldn't change the shop: ${err.message}`)
    }
  }

  // Faults outlive a page reload, so the closed section still has to say one is active.
  const failing = shops?.filter((shop) => shop.fault !== 'none').length ?? 0

  return (
    <section aria-label="Demo controls" className="failure-switch">
      {error && <p role="alert">{error}</p>}
      <details>
        <summary>Demo controls{failing > 0 && ` (${failing} failing)`}</summary>
        <h3>Failure switch</h3>
        <p>Takes effect immediately, including during a call. All three shops are fictional.</p>
        {shops?.map((shop) => (
          <div
            key={shop.shopId}
            className={shop.fault === 'none' ? 'shop-control' : 'shop-control shop-control-failing'}
          >
            <label htmlFor={`fault-${shop.shopId}`}>{shop.name}</label>
            <span>{shop.openBays} open bays</span>
            <select
              id={`fault-${shop.shopId}`}
              value={shop.fault}
              onChange={(event) => setFault(shop.shopId, event.target.value)}
            >
              {FAULTS.map((fault) => (
                <option key={fault.value} value={fault.value}>
                  {fault.label}
                </option>
              ))}
            </select>
          </div>
        ))}
      </details>
    </section>
  )
}

export default FailureSwitch

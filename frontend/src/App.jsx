import { useEffect, useState } from 'react'
import './App.css'

async function createIssue(idempotencyKey, signal) {
  const res = await fetch('/api/issues', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    signal,
  })
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
  return res.json()
}

function App() {
  // One key per page load. Retries and StrictMode's double-run reuse it, and
  // the backend treats a repeated key as the same issue.
  const [idempotencyKey] = useState(() => crypto.randomUUID())
  const [attempt, setAttempt] = useState(0)
  const [issue, setIssue] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    createIssue(idempotencyKey, controller.signal)
      .then((created) => {
        setIssue(created)
        setError(null)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
    return () => controller.abort()
  }, [idempotencyKey, attempt])

  return (
    <main className="issue-page">
      <h1>Elmeeda</h1>
      {issue && (
        <section role="status">
          <h2>Issue created</h2>
          <dl>
            <dt>ID</dt>
            <dd>{issue.issueId}</dd>
          </dl>
        </section>
      )}
      {!issue && !error && <p role="status">Creating issue…</p>}
      {!issue && error && (
        <section role="alert">
          <h2>Couldn't create the issue</h2>
          <p>{error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null)
              setAttempt((n) => n + 1)
            }}
          >
            Try again
          </button>
        </section>
      )}
    </main>
  )
}

export default App

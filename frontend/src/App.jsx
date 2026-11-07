import { useEffect, useState } from 'react'
import './App.css'

async function createIssue(id, signal) {
  const res = await fetch('/api/issues', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
    signal,
  })
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
  return res.json()
}

function App() {
  // One GUID per page load. Retries and StrictMode's double-run reuse it, and
  // the backend treats a repeated GUID as the same issue.
  const [guid] = useState(() => crypto.randomUUID())
  const [attempt, setAttempt] = useState(0)
  const [issue, setIssue] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    createIssue(guid, controller.signal)
      .then((created) => {
        setIssue(created)
        setError(null)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
    return () => controller.abort()
  }, [guid, attempt])

  return (
    <main className="issue-page">
      <h1>Elmeeda</h1>
      {issue && (
        <section role="status">
          <h2>Issue created</h2>
          <dl>
            <dt>ID</dt>
            <dd>{issue.id}</dd>
            <dt>Status</dt>
            <dd>{issue.status}</dd>
            <dt>Created</dt>
            <dd>{new Date(issue.created_at).toLocaleString()}</dd>
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

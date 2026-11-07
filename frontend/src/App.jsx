import { useEffect, useRef, useState } from 'react'
import './App.css'

async function createIssue() {
  const res = await fetch('/api/issues', { method: 'POST' })
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
  return res.json()
}

function App() {
  const [attempt, setAttempt] = useState(0)
  const [issue, setIssue] = useState(null)
  const [error, setError] = useState(null)
  // Every POST creates a new issue, so StrictMode's second effect run must not send one.
  const lastAttempt = useRef(null)

  useEffect(() => {
    if (lastAttempt.current === attempt) return
    lastAttempt.current = attempt
    createIssue()
      .then((created) => {
        setIssue(created)
        setError(null)
      })
      .catch((err) => setError(err.message))
  }, [attempt])

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

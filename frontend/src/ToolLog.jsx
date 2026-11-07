function pretty(value) {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

function ToolLog({ entries }) {
  return (
    <section aria-label="Tool call log" className="tool-log">
      <h3>Tool call log</h3>
      {entries.length === 0 && <p>No tool calls yet.</p>}
      <ol>
        {entries.map((entry) => (
          <li key={entry.id} className={`tool-call tool-call-${entry.status}`}>
            <details>
              <summary>
                <code>{entry.name}</code>
                <span className="tool-status">
                  {entry.status === 'running' && 'running…'}
                  {entry.status === 'ok' && 'ok'}
                  {entry.status === 'error' && `error: ${entry.result.error}`}
                </span>
                <span className="tool-duration">
                  {entry.ms === undefined ? '' : `${entry.ms} ms`}
                </span>
              </summary>
              <h4>Arguments</h4>
              <pre>{pretty(entry.args)}</pre>
              {entry.status !== 'running' && (
                <>
                  <h4>{entry.status === 'error' ? 'Error' : 'Result'}</h4>
                  <pre>{pretty(entry.result)}</pre>
                </>
              )}
            </details>
          </li>
        ))}
      </ol>
    </section>
  )
}

export default ToolLog

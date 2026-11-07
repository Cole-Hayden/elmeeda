// Runs the model's tool calls and reports what the dispatcher says, without knowing about
// WebRTC or React, so the rules below can be tested on their own. The backend decides whether a
// booking is allowed; this only makes sure it hears the dispatcher's words in time.

const TRANSCRIPT_WAIT_MS = 5000

function wait(ms) {
  let timer
  const promise = new Promise((resolve) => {
    timer = setTimeout(resolve, ms)
  })
  return { promise, cancel: () => clearTimeout(timer) }
}

export function createToolRelay({ post, onLog = () => {}, now = () => performance.now() }) {
  let nextLogId = 1
  // What the agent is reading back, set once the model has received it.
  let readingBack = null
  // The read-back the dispatcher is currently answering, set once its audio has finished playing.
  let confirmationId = null
  // What the agent said in responses that may still be playing, by response.
  const said = new Map()
  // Replies still being transcribed, by conversation item.
  const replies = new Map()
  let answers = Promise.resolve()

  const logged = async (name, args, run) => {
    const entry = { id: nextLogId++, name, args, status: 'running', startedAt: Date.now() }
    onLog(entry)
    const started = now()
    const result = await run()
    onLog({
      ...entry,
      result,
      status: result?.error ? 'error' : 'ok',
      ms: Math.round(now() - started),
    })
    return result
  }

  const runTool = (name, args) => logged(name, args, () => post(`tools/${name}`, args))

  // A call that relies on the dispatcher's yes has to wait until the backend has heard it.
  const repliesRecorded = async () => {
    if (replies.size > 0) {
      const { promise: timedOut, cancel } = wait(TRANSCRIPT_WAIT_MS)
      await Promise.race([Promise.all([...replies.values()].map((reply) => reply.done)), timedOut])
      cancel()
    }
    await answers
  }

  // A dropped response might still have booked, and retrying can't double-book, because the
  // backend returns the existing booking. So a lost answer is asked for once more.
  const bookRepair = async (args) => {
    await repliesRecorded()
    const result = await runTool('book_repair', args)
    if (result.error !== 'tool_failed') return result
    return runTool('book_repair', args)
  }

  return {
    // Returns the result to show on screen. The model gets `forModel(result)`.
    async run(name, rawArgs) {
      let args
      try {
        args = JSON.parse(rawArgs)
      } catch {
        return logged(name, rawArgs, async () => ({ error: 'invalid_arguments' }))
      }
      if (name === 'book_repair') return bookRepair(args)
      if (name === 'update_issue') await repliesRecorded()
      const result = await runTool(name, args)
      if (name === 'prepare_booking' || result.confirmationId) {
        readingBack = null
        confirmationId = null
      }
      return result
    },

    // Call this as the result is handed to the model. Whatever the agent said before this can't
    // be the read-back, because it didn't have the details yet.
    delivered(_name, result) {
      if (!result.confirmationId) return
      readingBack = result.confirmationId
      said.clear()
    },

    agentSaid(responseId, text) {
      const earlier = said.get(responseId)
      said.set(responseId, earlier ? `${earlier} ${text}` : text)
    },

    // The dispatcher has now heard this response, so it can count as the read-back, and only
    // speech that starts after this can answer it. "Okay" said while the agent is still reading
    // doesn't count, and neither does a "yes" said while picking the shop, however late its
    // transcript arrives. Sent through the same queue as replies, so the backend hears them in
    // the order they happened.
    playbackStopped(responseId) {
      const text = said.get(responseId)
      said.delete(responseId)
      if (!readingBack || !text) return
      const id = readingBack
      confirmationId = id
      answers = answers.then(() =>
        logged('read_back_check', { text }, () =>
          post('read-backs', { confirmationId: id, text }),
        ),
      )
    },

    // The dispatcher talked over this response, so they didn't hear all of it.
    playbackCleared(responseId) {
      said.delete(responseId)
    },

    speechStarted(itemId) {
      said.clear()
      if (!itemId || !confirmationId || replies.has(itemId)) return
      let settle
      const done = new Promise((resolve) => {
        settle = resolve
      })
      replies.set(itemId, { confirmationId, settle, done })
    },

    // Replies are sent in order, so the latest one decides.
    transcribed(itemId, text) {
      const reply = replies.get(itemId)
      if (!reply) return
      answers = answers.then(() =>
        logged('confirmation_answer', { text }, () =>
          post('answers', { confirmationId: reply.confirmationId, text }),
        ),
      )
      answers.finally(() => {
        replies.delete(itemId)
        reply.settle()
      })
    },

    // With no transcript there's no answer, so this reply can't confirm anything.
    transcriptionFailed(itemId) {
      const reply = replies.get(itemId)
      if (!reply) return
      replies.delete(itemId)
      reply.settle()
    },
  }
}

// The model doesn't need the confirmation ID, and has no way to use it.
export function forModel(result) {
  const { confirmationId: _confirmationId, ...rest } = result
  return rest
}

// The latest state of every log entry, in the order the calls started.
export function updateLog(log, entry) {
  const index = log.findIndex((item) => item.id === entry.id)
  if (index === -1) return [...log, entry]
  return log.map((item, i) => (i === index ? entry : item))
}

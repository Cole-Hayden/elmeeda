import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createToolRelay, forModel, updateLog } from './toolRelay.js'

const PREPARED = {
  confirmationId: 'c1',
  shopId: 's1',
  shopName: 'Rockdale',
  estimate: '1380.00',
  startTime: 't',
}

function setup(responses = {}) {
  const calls = []
  const log = []
  let clock = 0
  const relay = createToolRelay({
    post: async (path, body) => {
      calls.push({ path, body })
      const response = responses[path]
      if (Array.isArray(response)) return response.shift()
      return response ?? { ok: true }
    },
    onLog: (entry) => {
      log.splice(0, log.length, ...updateLog(log, entry))
    },
    now: () => (clock += 25),
  })
  return { relay, calls, log }
}

async function prepare(relay) {
  const result = await relay.run('prepare_booking', '{"shopId":"s1"}')
  relay.delivered('prepare_booking', result)
  return result
}

// The agent says the details and its audio finishes playing.
function readBack(relay, responseId = 'r1') {
  relay.agentSaid(responseId, 'Rockdale, $1,380, at 5:15 PM. Should I book it?')
  relay.playbackStopped(responseId)
}

const paths = (calls) => calls.map((call) => call.path)

test('a reply to a limit read-back is sent with its confirmation', async () => {
  const { relay, calls } = setup({
    'tools/update_issue': { confirmationId: 'limit1', limitChangeNeedsYes: { maxBudget: '5000' } },
  })

  const result = await relay.run('update_issue', '{"maxBudget":5000}')
  relay.delivered('update_issue', result)
  readBack(relay)
  relay.speechStarted('item1')
  relay.transcribed('item1', 'Yes.')
  await relay.run('update_issue', '{"maxBudget":5000}')

  assert.deepEqual(paths(calls), [
    'tools/update_issue',
    'read-backs',
    'answers',
    'tools/update_issue',
  ])
  assert.deepEqual(calls[2].body, { confirmationId: 'limit1', text: 'Yes.' })
})

test('a plain update does not cancel the booking read-back', async () => {
  const { relay, calls } = setup({
    'tools/prepare_booking': PREPARED,
    'tools/update_issue': { missingDetails: [] },
  })

  await prepare(relay)
  readBack(relay)
  const result = await relay.run('update_issue', '{"symptoms":"Leak"}')
  relay.delivered('update_issue', result)
  relay.speechStarted('item1')
  relay.transcribed('item1', 'Yes.')
  await relay.run('update_issue', '{}')

  assert.equal(calls.find((call) => call.path === 'answers').body.confirmationId, 'c1')
})

test('the model never sees a limit confirmation ID', () => {
  assert.deepEqual(forModel({ confirmationId: 'limit1', limitChangeNeedsYes: {} }), {
    limitChangeNeedsYes: {},
  })
})

test('logs each call with its arguments, result, and duration', async () => {
  const { relay, log } = setup({ 'tools/search_shops': { options: [] } })

  await relay.run('search_shops', '{"a":1}')

  assert.equal(log.length, 1)
  assert.equal(log[0].name, 'search_shops')
  assert.deepEqual(log[0].args, { a: 1 })
  assert.deepEqual(log[0].result, { options: [] })
  assert.equal(log[0].status, 'ok')
  assert.equal(log[0].ms, 25)
})

test('logs an error result as an error', async () => {
  const { relay, log } = setup({ 'tools/book_repair': { error: 'confirmation_required' } })

  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.equal(log[0].status, 'error')
})

test('logs arguments the model garbled, without calling the backend', async () => {
  const { relay, calls, log } = setup()

  const result = await relay.run('search_shops', '{not json')

  assert.equal(result.error, 'invalid_arguments')
  assert.equal(calls.length, 0)
  assert.equal(log[0].status, 'error')
})

test('a reply to the read-back is sent with its confirmation', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)
  readBack(relay)

  relay.speechStarted('i1')
  relay.transcribed('i1', 'Yes.')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.equal(calls[1].path, 'read-backs')
  assert.equal(calls[1].body.confirmationId, 'c1')
  assert.deepEqual(calls[2], { path: 'answers', body: { confirmationId: 'c1', text: 'Yes.' } })
  assert.equal(calls[3].path, 'tools/book_repair')
})

test('speech before the read-back does not count, however late its transcript', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })

  relay.speechStarted('early')
  await prepare(relay)
  readBack(relay)
  relay.transcribed('early', 'Yes, Rockdale.')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.deepEqual(paths(calls), ['tools/prepare_booking', 'read-backs', 'tools/book_repair'])
})

test('speech while the result is on its way to the model does not count', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })

  await relay.run('prepare_booking', '{"shopId":"s1"}')
  relay.speechStarted('i1')
  relay.delivered('prepare_booking', PREPARED)
  relay.transcribed('i1', 'Yes.')

  assert.ok(!paths(calls).includes('answers'))
})

test('speech before the agent has said anything does not count', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)

  relay.speechStarted('i1')
  relay.transcribed('i1', 'Okay.')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.deepEqual(paths(calls), ['tools/prepare_booking', 'tools/book_repair'])
})

test('an okay said over the read-back does not count, and neither does the read-back', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)

  relay.agentSaid('r1', 'Rockdale, $1,380, at 5:15 PM.')
  relay.speechStarted('i1')
  relay.playbackStopped('r1')
  relay.transcribed('i1', 'Okay.')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.deepEqual(paths(calls), ['tools/prepare_booking', 'tools/book_repair'])
})

test('a read-back cut off by an interruption does not count', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)

  relay.agentSaid('r1', 'Rockdale, $1,380, at 5:15 PM.')
  relay.playbackCleared('r1')
  relay.playbackStopped('r1')
  relay.speechStarted('i1')
  relay.transcribed('i1', 'Yes.')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.deepEqual(paths(calls), ['tools/prepare_booking', 'tools/book_repair'])
})

test('what the agent said before it had the details is not the read-back', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })

  const result = await relay.run('prepare_booking', '{"shopId":"s1"}')
  relay.agentSaid('r0', 'Let me check that.')
  relay.delivered('prepare_booking', result)
  relay.playbackStopped('r0')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.deepEqual(paths(calls), ['tools/prepare_booking', 'tools/book_repair'])
})

test('a response in several parts is sent as one read-back', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)

  relay.agentSaid('r1', 'Rockdale, $1,380.')
  relay.agentSaid('r1', 'Starting at 5:15 PM.')
  relay.playbackStopped('r1')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.equal(calls[1].body.text, 'Rockdale, $1,380. Starting at 5:15 PM.')
})

test('the agent reading it back a second time is sent too', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)

  readBack(relay, 'r1')
  readBack(relay, 'r2')
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.deepEqual(paths(calls), [
    'tools/prepare_booking',
    'read-backs',
    'read-backs',
    'tools/book_repair',
  ])
})

test('nothing the agent says is sent when no booking is being read back', async () => {
  const { relay, calls } = setup()

  readBack(relay)
  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.deepEqual(paths(calls), ['tools/book_repair'])
})

test('booking waits for a reply still being transcribed', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)
  readBack(relay)
  relay.speechStarted('i1')

  const booking = relay.run('book_repair', '{"shopId":"s1"}')
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.deepEqual(paths(calls), ['tools/prepare_booking', 'read-backs'])

  relay.transcribed('i1', 'Yes.')
  await booking

  assert.deepEqual(paths(calls), [
    'tools/prepare_booking',
    'read-backs',
    'answers',
    'tools/book_repair',
  ])
})

test('a reply that could not be transcribed releases the booking without an answer', async () => {
  const { relay, calls } = setup({ 'tools/prepare_booking': PREPARED })
  await prepare(relay)
  readBack(relay)
  relay.speechStarted('i1')

  const booking = relay.run('book_repair', '{"shopId":"s1"}')
  relay.transcriptionFailed('i1')
  await booking

  assert.deepEqual(paths(calls), ['tools/prepare_booking', 'read-backs', 'tools/book_repair'])
})

test('a reply belongs to the read-back it answered, not a later one', async () => {
  const { relay, calls } = setup({
    'tools/prepare_booking': [PREPARED, { ...PREPARED, confirmationId: 'c2', shopId: 's2' }],
  })
  await prepare(relay)
  readBack(relay)
  relay.speechStarted('i1')
  await prepare(relay)

  relay.transcribed('i1', 'Yes.')
  await relay.run('book_repair', '{"shopId":"s2"}')

  assert.equal(calls.find((call) => call.path === 'answers').body.confirmationId, 'c1')
})

test('a booking whose answer was lost is asked for once more', async () => {
  const { relay, calls } = setup({
    'tools/book_repair': [{ error: 'tool_failed' }, { bookingId: 'BK-1', alreadyBooked: true }],
  })

  const result = await relay.run('book_repair', '{"shopId":"s1"}')

  assert.equal(result.bookingId, 'BK-1')
  assert.equal(calls.length, 2)
})

test('a refused booking is not retried', async () => {
  const { relay, calls } = setup({ 'tools/book_repair': { error: 'confirmation_required' } })

  await relay.run('book_repair', '{"shopId":"s1"}')

  assert.equal(calls.length, 1)
})

test('the model never sees the confirmation ID', () => {
  assert.equal('confirmationId' in forModel(PREPARED), false)
  assert.equal(forModel(PREPARED).estimate, '1380.00')
})

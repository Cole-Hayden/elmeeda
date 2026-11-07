import assert from 'node:assert/strict'
import { test } from 'node:test'
import { humanize } from './bookingList.js'

test('turns API values into labels', () => {
  assert.equal(humanize('coolant_leak'), 'Coolant leak')
  assert.equal(humanize('unknown'), 'Unknown')
})

test('shows a dash for an unknown value', () => {
  assert.equal(humanize(null), '—')
})

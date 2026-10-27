import assert from 'node:assert/strict'
import { test } from 'node:test'
import { moonPhase, subpoint } from './sky.ts'

// Independent check: on 2026-10-25 the sun's declination is about -12.4 degrees and the equation of time about +16 min,
// so at 12:00 UTC the sun is about 4 degrees west of Greenwich.
test('subsolar point on 2026-10-25 12:00 UTC', () => {
  const s = subpoint('Sun', new Date('2026-10-25T12:00:00Z'))
  assert.ok(Math.abs(s.lat - -12.4) < 0.5, `lat ${s.lat}`)
  assert.ok(Math.abs(s.lng - -4.1) < 0.7, `lng ${s.lng}`)
})

test('subsolar longitude moves 15 degrees west per hour', () => {
  const a = subpoint('Sun', new Date('2026-10-25T12:00:00Z')).lng
  const b = subpoint('Sun', new Date('2026-10-25T13:00:00Z')).lng
  assert.ok(Math.abs(a - b - 15) < 0.1)
})

test('moon is full near a known full moon and new near a known new moon', () => {
  assert.ok(moonPhase(new Date('2026-10-26T04:12:00Z')).illumination > 0.97) // full moon 2026-10-26
  assert.ok(moonPhase(new Date('2026-11-09T21:00:00Z')).illumination < 0.05) // new moon ~2026-11-09
})

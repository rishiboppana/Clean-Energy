import assert from 'node:assert/strict'
import { test } from 'node:test'
import { absorbable } from './absorbable.ts'

test('limited by headroom', () => assert.deepEqual(absorbable(1800, 1200), { mw: 1200, share: 1 }))
test('limited by surplus', () => assert.deepEqual(absorbable(300, 450), { mw: 300, share: 300 / 450 }))
test('no surplus is red', () => assert.deepEqual(absorbable(0, 500), { mw: 0, share: 0 }))
test('negative surplus clamps to zero', () => assert.equal(absorbable(-5, 500).mw, 0))

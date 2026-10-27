import assert from 'node:assert/strict'
import { test } from 'node:test'
import { place } from './placement.ts'

const nodes = [
  { id: 'atl', grid: 'SOCO', mw: 0 },
  { id: 'dfw', grid: 'ERCOT', mw: 850 },
  { id: 'nova', grid: 'PJM', mw: 1200 },
  { id: 'chi', grid: 'PJM', mw: 750 },
]
const fleets = { atl: { gpu_type: 'H100', gpu_count: 100 }, dfw: { gpu_type: 'H100', gpu_count: 100 }, nova: { gpu_type: 'H100', gpu_count: 100 }, chi: { gpu_type: 'A100', gpu_count: 100 } }
const job = { gpu_type: 'H100', gpu_count: 8, power_kw: { max: 15 } }

test('stays home when its surplus covers the job', () => assert.deepEqual(place(job, 'dfw', nodes, fleets), { kind: 'home', dest: 'dfw' }))
test('moves to the hub with the most absorbable surplus when home has none', () => assert.deepEqual(place(job, 'atl', nodes, fleets), { kind: 'moved', dest: 'nova' }))
test('respects GPU type: an A100 job can only go to an A100 hub', () => assert.deepEqual(place({ ...job, gpu_type: 'A100' }, 'atl', nodes, fleets), { kind: 'moved', dest: 'chi' }))
test('respects allowed grids (privacy)', () => assert.deepEqual(place({ ...job, allowed_grids: ['ERCOT'] }, 'atl', nodes, fleets), { kind: 'moved', dest: 'dfw' }))
test('too few GPUs at every hub: nothing covered, stays home', () => assert.deepEqual(place({ ...job, gpu_count: 1000 }, 'atl', nodes, fleets), { kind: 'none', dest: 'atl' }))
test('no surplus anywhere: stays home as normal load', () => assert.deepEqual(place(job, 'atl', nodes.map((n) => ({ ...n, mw: 0 })), fleets), { kind: 'none', dest: 'atl' }))

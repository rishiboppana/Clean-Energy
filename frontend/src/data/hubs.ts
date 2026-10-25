// Headroom values are placeholder assumptions (specs.md section 3).
import registry from '../../../data/hubs.json'

export type Quality = 'measured' | 'proxy' | 'estimate' | 'simulated'

export interface Hub {
  id: string
  name: string
  grid: string
  lon: number
  lat: number
  headroomMw: number
}

// Registry source of truth: data/hubs.json at the repo root (also loaded into Postgres later).
export const HUBS: Hub[] = registry.hubs.map((h) => ({
  id: h.id,
  name: h.name,
  grid: h.grid,
  lon: h.lon,
  lat: h.lat,
  headroomMw: h.headroom_mw,
}))

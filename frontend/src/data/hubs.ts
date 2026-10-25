// Section 3 of specs.md. Headroom values are placeholder assumptions.
export type Quality = 'measured' | 'proxy' | 'estimate' | 'simulated'

export interface Hub {
  id: string
  name: string
  grid: string
  lon: number
  lat: number
  headroomMw: number
}

export const HUBS: Hub[] = [
  { id: 'nova', name: 'Northern Virginia', grid: 'PJM', lon: -77.49, lat: 39.04, headroomMw: 1200 },
  { id: 'columbus', name: 'Greater Columbus', grid: 'PJM', lon: -83.0, lat: 39.96, headroomMw: 900 },
  { id: 'chicago', name: 'Greater Chicago', grid: 'PJM', lon: -87.63, lat: 41.88, headroomMw: 750 },
  { id: 'dfw', name: 'Dallas-Fort Worth', grid: 'ERCOT', lon: -96.8, lat: 32.78, headroomMw: 850 },
  { id: 'svalley', name: 'Silicon Valley', grid: 'CAISO', lon: -121.96, lat: 37.35, headroomMw: 350 },
  { id: 'phoenix', name: 'Phoenix-Mesa', grid: 'SRP', lon: -111.84, lat: 33.42, headroomMw: 600 },
  { id: 'iowa', name: 'Central Iowa', grid: 'MISO', lon: -93.47, lat: 41.66, headroomMw: 450 },
  { id: 'atlanta', name: 'Atlanta Metro', grid: 'SOCO', lon: -84.75, lat: 33.75, headroomMw: 500 },
  { id: 'quincy', name: 'Quincy / Columbia Basin', grid: 'GCPD', lon: -119.85, lat: 47.23, headroomMw: 400 },
  { id: 'slc', name: 'Salt Lake Valley', grid: 'PACE', lon: -111.89, lat: 40.76, headroomMw: 350 },
]

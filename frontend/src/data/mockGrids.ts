// MOCK data until the API exists (I1 in specs.md section 12b). Replace with GET /v1/grids.
import type { Quality } from './hubs'

export const MOCK_GRIDS: Record<string, { surplusMw: number; demandMw: number; quality: Quality }> = {
  PJM: { demandMw: 90000, surplusMw: 1800, quality: 'proxy' },
  ERCOT: { demandMw: 55000, surplusMw: 1400, quality: 'proxy' },
  CAISO: { demandMw: 25000, surplusMw: 600, quality: 'measured' },
  SRP: { demandMw: 6000, surplusMw: 0, quality: 'estimate' },
  MISO: { demandMw: 85000, surplusMw: 300, quality: 'proxy' },
  SOCO: { demandMw: 28000, surplusMw: 0, quality: 'estimate' },
  GCPD: { demandMw: 1500, surplusMw: 900, quality: 'proxy' },
  PACE: { demandMw: 7000, surplusMw: 100, quality: 'estimate' },
}

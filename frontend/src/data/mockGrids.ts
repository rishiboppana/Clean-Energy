// MOCK data until the API exists (I1 in specs.md section 12b). Replace with GET /v1/grids.
import type { Quality } from './hubs'

export const MOCK_GRIDS: Record<string, { surplusMw: number; quality: Quality }> = {
  PJM: { surplusMw: 1800, quality: 'proxy' },
  ERCOT: { surplusMw: 1400, quality: 'proxy' },
  CAISO: { surplusMw: 600, quality: 'measured' },
  SRP: { surplusMw: 0, quality: 'estimate' },
  MISO: { surplusMw: 300, quality: 'proxy' },
  SOCO: { surplusMw: 0, quality: 'estimate' },
  GCPD: { surplusMw: 900, quality: 'proxy' },
  PACE: { surplusMw: 100, quality: 'estimate' },
}

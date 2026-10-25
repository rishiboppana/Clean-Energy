// MOCK data until the API exists. Shapes follow specs.md: ledger (SC11), /v1/health, jobs (section 12b).
import type { Quality } from './hubs'

// Ledger totals for today. Unabsorbed is split by reason (SC10); the invariant holds by construction.
export const MOCK_LEDGER = {
  jobsMwh: 120,
  coolingMwh: 60,
  fillerMwh: 40,
  unabsorbed: { headroom_full: 220, tank_full: 50, no_eligible_work: 40 },
}

export const MOCK_JOBS = { moved: 14, held: 5, homeRun: 9, missed: 0, shortfallMwh: 1.2 }

export const MOCK_CARBON_AVOIDED_T = 84 // grid-average attribution (H6), not marginal

export const MOCK_FRESHNESS: { source: string; ageH: number; verdict: 'fresh' | 'slow' | 'stale' }[] = [
  { source: 'CAISO', ageH: 0.2, verdict: 'fresh' },
  { source: 'ERCOT', ageH: 1.1, verdict: 'fresh' },
  { source: 'MISO', ageH: 0.4, verdict: 'fresh' },
  { source: 'EIA (PJM, SRP, SOCO, GCPD, PACE)', ageH: 26, verdict: 'slow' },
  { source: 'Open-Meteo', ageH: 3.5, verdict: 'stale' },
]

// Deterministic fake series for the forecast-vs-actual chart: 12 h of actuals, then 12 h of forecast with a band.
export function mockSeries(surplusMw: number, quality: Quality) {
  const base = Math.max(surplusMw, 100)
  const at = (h: number) => base * (0.7 + 0.3 * Math.sin(h / 3))
  const hours = Array.from({ length: 25 }, (_, i) => i - 12)
  return {
    quality,
    actual: hours.filter((h) => h <= 0).map((h) => ({ h, v: at(h) * 1.04 })),
    forecast: hours
      .filter((h) => h >= 0)
      .map((h) => ({ h, p10: at(h) * (1 - 0.05 * h), p50: at(h), p90: at(h) * (1 + 0.05 * h) })),
  }
}

// Placement preview: stay at the user's hub if surplus can cover the job, else move it to a hub that can (specs.md SC4, SC5, SC13).
// Surplus-only rule: absorbable MW at the hub must cover the job's MAX power. No covered hub means the job stays home as normal load (SC7).
// shortcut: no deadline/transfer-time/latency-class check and no forecast band, upgrade when the scheduler exists.
export interface Estimate {
  gpu_type: string | null
  gpu_count: number | null
  power_kw: { max: number }
  allowed_grids?: string[] | 'all'
}
export interface Candidate {
  id: string
  grid: string
  mw: number // absorbable now
}
export type Fleets = Record<string, { gpu_type: string; gpu_count: number }>

export type Placement =
  | { kind: 'home'; dest: string }
  | { kind: 'moved'; dest: string }
  | { kind: 'none'; dest: string } // nothing covered: runs at home as normal load

export function place(job: Estimate, homeId: string, nodes: Candidate[], fleets: Fleets): Placement {
  const need = job.power_kw.max / 1000
  const ok = (n: Candidate) => {
    const f = fleets[n.id]
    const gpuOk = !job.gpu_type || (f?.gpu_type === job.gpu_type && f.gpu_count >= (job.gpu_count ?? 0))
    const gridOk = !job.allowed_grids || job.allowed_grids === 'all' || job.allowed_grids.includes(n.grid)
    return n.mw >= need && gpuOk && gridOk
  }
  const home = nodes.find((n) => n.id === homeId)
  if (home && ok(home)) return { kind: 'home', dest: homeId }
  // most absorbable surplus first, then id so the result is reproducible (SC5)
  const best = nodes.filter(ok).sort((a, b) => b.mw - a.mw || a.id.localeCompare(b.id))[0]
  return best ? { kind: 'moved', dest: best.id } : { kind: 'none', dest: homeId }
}

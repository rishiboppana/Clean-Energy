import { MOCK_LEDGER, MOCK_NODE_JOBS, MOCK_TANK } from '../../data/mockDashboard'
import { MOCK_GRIDS } from '../../data/mockGrids'
import { Badge } from './Badge'
import { ForecastChart } from './ForecastChart'
import { absorbable } from '../map/absorbable'
import type { MapNode } from '../map/nodes'

const T_ABS = 50 // G2 placeholders
const T_PCT = 0.005
const totalSurplus = Object.values(MOCK_GRIDS).reduce((s, g) => s + g.surplusMw, 0)

interface Props {
  node: MapNode
  isHome: boolean
  onSetHome: () => void
  onBack: () => void
}

// FE9: node detail replaces the dashboard while a node is selected.
export function NodeDetail({ node, isHome, onSetHome, onBack }: Props) {
  const grid = MOCK_GRIDS[node.grid]
  const oversupply = grid.surplusMw >= Math.max(T_ABS, T_PCT * grid.demandMw) // G2
  const { mw } = absorbable(grid.surplusMw, node.headroomMw)
  const limit = grid.surplusMw < node.headroomMw ? 'grid surplus' : 'hub headroom'
  const tank = MOCK_TANK[node.id]
  const jobs = MOCK_NODE_JOBS[node.id] ?? []

  // Mock ledger: the global buckets split by this grid's share of surplus. Sum check is real arithmetic on those numbers.
  const k = totalSurplus ? grid.surplusMw / totalSurplus : 0
  const L = {
    Jobs: MOCK_LEDGER.jobsMwh * k, Cooling: MOCK_LEDGER.coolingMwh * k, Filler: MOCK_LEDGER.fillerMwh * k,
    Unabsorbed: Object.values(MOCK_LEDGER.unabsorbed).reduce((s, v) => s + v, 0) * k,
  }
  const ledgerTotal = Object.values(L).reduce((s, v) => s + v, 0)

  return (
    <aside className="panel" aria-label={`${node.name} details`}>
      <button className="back" onClick={onBack}>← Dashboard</button>
      <h2>{node.name}</h2>
      <p className="sub">
        Grid {node.grid} <span className={`state ${oversupply ? 'over' : 'normal'}`}>{oversupply ? 'Oversupply' : 'Normal'}</span>{' '}
        <Badge q={node.quality} />
      </p>

      <section>
        <h3>Surplus now <Badge q={node.quality} /></h3>
        <p className="big">{grid.surplusMw.toLocaleString()} MW</p>
        <p className="sub">P10 to P90: {Math.round(grid.surplusMw * 0.7).toLocaleString()} to {Math.round(grid.surplusMw * 1.3).toLocaleString()} MW (mock band)</p>
        <ForecastChart surplusMw={grid.surplusMw} quality={node.quality} />
        <p className="sub">Shared by every hub on {node.grid}.</p>
      </section>

      <section>
        <h3>Absorbable now <Badge q="estimate" /></h3>
        <p className="big">{Math.round(mw)} MW</p>
        <p className="sub">Grid surplus {grid.surplusMw} MW, hub headroom {node.headroomMw} MW <Badge q="assumption" /></p>
        <p className="sub">Limited by {mw === 0 ? 'no surplus' : limit}.</p>
      </section>

      <section>
        <h3>Cooling tank <Badge q="simulated" /></h3>
        <div className="gauge" role="meter" aria-valuenow={tank.levelPct} aria-valuemin={0} aria-valuemax={100} aria-label="Tank level">
          <i style={{ width: `${tank.levelPct}%` }} />
        </div>
        <p className="sub">{tank.levelPct}% full, chiller {tank.chiller}</p>
      </section>

      <section>
        <h3>Jobs on this node <Badge q="simulated" /></h3>
        {jobs.length === 0 ? (
          <p className="sub">No jobs on this node.</p>
        ) : (
          <ul className="joblist">
            {jobs.map((j) => (
              <li key={j.id}><b>{j.id}</b> <span className={`jobstate ${j.state}`}>{j.state}</span><br />{j.window}, {j.mw} MW</li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3>Ledger for {node.grid} today <Badge q="simulated" /></h3>
        <ul className="legend">
          {Object.entries(L).map(([name, v]) => <li key={name}>{name} {v.toFixed(1)} MWh</li>)}
        </ul>
        <p className="sub">Sum {ledgerTotal.toFixed(1)} MWh, check OK. Mock split of the global ledger.</p>
      </section>

      <button className="primary" onClick={onSetHome} disabled={isHome}>{isHome ? '✓ This is my location' : 'Set as my location'}</button>
      <footer>Hub headroom is a placeholder. Hubs are modeled clusters, not any company's sites. All values are mock data.</footer>
    </aside>
  )
}

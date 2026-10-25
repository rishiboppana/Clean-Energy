import { HUBS } from '../../data/hubs'
import { MOCK_CARBON_AVOIDED_T, MOCK_FRESHNESS, MOCK_JOBS, MOCK_LEDGER } from '../../data/mockDashboard'
import { MOCK_GRIDS } from '../../data/mockGrids'
import { Badge } from './Badge'
import { ForecastChart } from './ForecastChart'

const grids = Object.entries(MOCK_GRIDS)
const surplusTotal = grids.reduce((s, [, g]) => s + g.surplusMw, 0)
const caisoMw = MOCK_GRIDS.CAISO.surplusMw

// FE5 at grid level: a grid can absorb at most the combined headroom of its hubs.
const topGrids = grids
  .map(([id, g]) => ({
    id,
    mw: Math.min(g.surplusMw, HUBS.filter((h) => h.grid === id).reduce((s, h) => s + h.headroomMw, 0)),
  }))
  .sort((a, b) => b.mw - a.mw)
const topMax = Math.max(...topGrids.map((g) => g.mw), 1)

const { jobsMwh, coolingMwh, fillerMwh, unabsorbed } = MOCK_LEDGER
const unabsorbedMwh = Object.values(unabsorbed).reduce((s, v) => s + v, 0)
const absorbedMwh = jobsMwh + coolingMwh + fillerMwh
const totalMwh = absorbedMwh + unabsorbedMwh // ledger invariant (SC11): buckets sum to surplus
const buckets = [
  ['Jobs', jobsMwh, 'jobs'],
  ['Cooling', coolingMwh, 'cooling'],
  ['Filler', fillerMwh, 'filler'],
  ['Unabsorbed', unabsorbedMwh, 'unabsorbed'],
] as const

export function Dashboard({ lastGrid }: { lastGrid: string | null }) {
  return (
    <aside className="panel">
      <h2>Dashboard</h2>

      <section>
        <h3>Surplus now <Badge q="proxy" /></h3>
        <p className="big">{surplusTotal.toLocaleString()} MW</p>
        <p className="sub">CAISO {caisoMw} MW <Badge q="measured" />, other grids proxy</p>
      </section>

      <section>
        <h3>Absorbed today <Badge q="simulated" /></h3>
        <p className="big">
          {absorbedMwh} MWh <span className="sub">({Math.round((absorbedMwh / totalMwh) * 100)}% of surplus)</span>
        </p>
        <div className="stack" role="img" aria-label="Ledger buckets">
          {buckets.map(([name, v, cls]) => (
            <span key={name} className={`seg ${cls}`} style={{ flexGrow: v }} title={`${name} ${v} MWh`} />
          ))}
        </div>
        <ul className="legend">
          {buckets.map(([name, v, cls]) => (
            <li key={name}><i className={`dot ${cls}`} />{name} {v} MWh</li>
          ))}
        </ul>
        <p className="sub">
          Unabsorbed: {Object.entries(unabsorbed).map(([r, v]) => `${r.replaceAll('_', ' ')} ${v}`).join(', ')}
        </p>
      </section>

      <section>
        <h3>Jobs <Badge q="simulated" /></h3>
        <dl className="grid4">
          <div><dt>Moved</dt><dd>{MOCK_JOBS.moved}</dd></div>
          <div><dt>Held</dt><dd>{MOCK_JOBS.held}</dd></div>
          <div><dt>Ran at home</dt><dd>{MOCK_JOBS.homeRun}</dd></div>
          <div className={MOCK_JOBS.missed ? 'alert' : ''}><dt>Deadline misses</dt><dd>{MOCK_JOBS.missed}</dd></div>
        </dl>
        <p className="sub">Shortfall {MOCK_JOBS.shortfallMwh} MWh</p>
      </section>

      <section>
        <h3>Top grids by absorbable surplus <Badge q="proxy" /></h3>
        {topGrids.map((g) => (
          <div key={g.id} className="bar-row">
            <span>{g.id}</span>
            <span className="bar"><i style={{ width: `${(g.mw / topMax) * 100}%` }} /></span>
            <span>{g.mw} MW</span>
          </div>
        ))}
        <p className="sub">Hub headroom values are placeholders.</p>
      </section>

      <section>
        <h3>Carbon avoided <Badge q="estimate" /></h3>
        <p className="big">{MOCK_CARBON_AVOIDED_T} tCO₂</p>
        <p className="sub">Grid-average intensity, not marginal.</p>
      </section>

      <section>
        <h3>Data freshness</h3>
        <table>
          <tbody>
            {MOCK_FRESHNESS.map((f) => (
              <tr key={f.source}>
                <td>{f.source}</td>
                <td>{f.ageH} h</td>
                <td className={`v-${f.verdict}`}>{f.verdict}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Forecast vs actual {lastGrid && <>· {lastGrid} </>}<Badge q={lastGrid ? MOCK_GRIDS[lastGrid].quality : 'simulated'} /></h3>
        {lastGrid ? (
          <ForecastChart surplusMw={MOCK_GRIDS[lastGrid].surplusMw} quality={MOCK_GRIDS[lastGrid].quality} />
        ) : (
          <p className="sub">Click a node to see its grid.</p>
        )}
        <p className="sub">Line: actual then forecast P50. Shaded: P10 to P90.</p>
      </section>

      <footer>Hubs are modeled clusters, not any company's sites or capacity. Absorbed figures are simulated what-ifs. All values on this screen are mock data.</footer>
    </aside>
  )
}

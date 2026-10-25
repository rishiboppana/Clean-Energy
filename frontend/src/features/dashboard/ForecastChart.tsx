import { mockSeries } from '../../data/mockDashboard'

const W = 300
const H = 100

export function ForecastChart({ surplusMw, quality }: { surplusMw: number; quality: Parameters<typeof mockSeries>[1] }) {
  const { actual, forecast } = mockSeries(surplusMw, quality)
  const max = Math.max(...forecast.map((f) => f.p90), ...actual.map((a) => a.v))
  const x = (h: number) => ((h + 12) / 24) * W
  const y = (v: number) => H - (v / max) * (H - 4) - 2
  const line = (pts: { h: number; v: number }[]) => pts.map((p) => `${x(p.h)},${y(p.v)}`).join(' ')
  const band =
    forecast.map((f) => `${x(f.h)},${y(f.p90)}`).join(' ') +
    ' ' +
    [...forecast].reverse().map((f) => `${x(f.h)},${y(f.p10)}`).join(' ')

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Actual surplus and forecast with P10 to P90 band">
      <polygon points={band} className="band" />
      <polyline points={line(actual)} className="actual" />
      <polyline points={line(forecast.map((f) => ({ h: f.h, v: f.p50 })))} className="forecast" />
      <line x1={x(0)} x2={x(0)} y1="0" y2={H} className="now" />
    </svg>
  )
}

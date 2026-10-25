import { geoAlbersUsa, geoPath } from 'd3-geo'
import type { Quality } from '../../data/hubs'
import { NODES, nodeColor } from './nodes'
import { states } from './states'

const W = 975
const H = 610
const projection = geoAlbersUsa().fitSize([W, H], states)
const path = geoPath(projection)

// FE7: solid = measured, dashed = proxy, dotted = estimated
const OUTLINE: Record<Quality, string | undefined> = {
  measured: undefined,
  proxy: '6 3',
  estimate: '2 3',
  simulated: '1 2',
}

export function FlatMap() {
  return (
    <svg className="map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="US map of modeled data center hubs">
      {states.features.map((s) => (
        <path key={s.id} className="state" d={path(s) ?? undefined} />
      ))}
      {NODES.map((n) => {
        const xy = projection([n.lon, n.lat])
        if (!xy) return null
        return (
          <circle
            key={n.id}
            className="node"
            tabIndex={0}
            cx={xy[0]}
            cy={xy[1]}
            r={6 + 10 * n.share} // FE6: size also grows with absorbable MW
            fill={nodeColor(n.share)}
            strokeDasharray={OUTLINE[n.quality]}
          >
            <title>{n.label}</title>
          </circle>
        )
      })}
    </svg>
  )
}

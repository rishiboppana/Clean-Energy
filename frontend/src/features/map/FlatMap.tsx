import { geoAlbersUsa, geoPath } from 'd3-geo'
import type { Quality } from '../../data/hubs'
import { NODES, nodeColor } from './nodes'
import type { MapNode, Move } from './nodes'
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

export function FlatMap({ selectedId, onSelect, move }: { selectedId: string | null; onSelect: (n: MapNode | null) => void; move: Move | null }) {
  const a = move && projection([move.from.lon, move.from.lat])
  const b = move && projection([move.to.lon, move.to.lat])
  // quadratic curve bowed upward, so the arrow reads as a flight path rather than a straight line
  const arc = a && b ? `M${a[0]},${a[1]} Q${(a[0] + b[0]) / 2},${(a[1] + b[1]) / 2 - Math.hypot(b[0] - a[0], b[1] - a[1]) * 0.25} ${b[0]},${b[1]}` : null
  return (
    <svg className="map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="US map of modeled data center hubs" onClick={() => onSelect(null)}>
      <defs>
        <marker id="arrowhead" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--arc)" />
        </marker>
      </defs>
      {states.features.map((s) => (
        <path key={s.id} className="state" d={path(s) ?? undefined} />
      ))}
      {NODES.map((n) => {
        const xy = projection([n.lon, n.lat])
        if (!xy) return null
        const r = 6 + 10 * n.share // FE6: size also grows with absorbable MW
        return (
          <g key={n.id}>
            {n.id === selectedId && <circle className="ring" cx={xy[0]} cy={xy[1]} r={r + 6} />}
            <circle
              className="node"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation() // a click on empty map deselects, a click on a node must not
                onSelect(n)
              }}
              onKeyDown={(e) => e.key === 'Enter' && onSelect(n)}
              cx={xy[0]}
              cy={xy[1]}
              r={r}
              fill={nodeColor(n.share)}
              strokeDasharray={OUTLINE[n.quality]}
            >
              <title>{n.label}</title>
            </circle>
          </g>
        )
      })}
      {arc && <path className="arc" d={arc} markerEnd="url(#arrowhead)" />}
    </svg>
  )
}

// FE26: nodes are defined once here and rendered by both the flat and globe views.
import { HUBS } from '../../data/hubs'
import type { Hub, Quality } from '../../data/hubs'
import { MOCK_GRIDS } from '../../data/mockGrids'
import { absorbable } from './absorbable'

export interface MapNode extends Hub {
  mw: number
  share: number
  quality: Quality
  label: string
}

export const NODES: MapNode[] = HUBS.map((h) => {
  const g = MOCK_GRIDS[h.grid]
  const { mw, share } = absorbable(g.surplusMw, h.headroomMw)
  return {
    ...h,
    mw,
    share,
    quality: g.quality,
    label: `${h.name} (${h.grid}): ${Math.round(mw)} MW absorbable, ${g.quality}. Headroom is a placeholder.`,
  }
})

// Hex, not hsl(): three.js (globe) cannot parse CSS hsl() strings. Hue 0 (red) to 120 (green).
export const nodeColor = (share: number) => {
  const h = 120 * share
  const [s, l] = [0.8, 0.45]
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const c = l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return Math.round(255 * c).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

// A job being moved from the user's hub to the hub chosen for it; drawn as a dotted arrow on both maps.
export interface Move {
  from: MapNode
  to: MapNode
}

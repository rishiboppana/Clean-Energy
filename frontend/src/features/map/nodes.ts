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

export const nodeColor = (share: number) => `hsl(${120 * share} 80% 45%)`

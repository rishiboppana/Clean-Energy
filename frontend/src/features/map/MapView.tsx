import { lazy, Suspense, useState } from 'react'
import { FlatMap } from './FlatMap'
import type { MapNode, Move } from './nodes'

const GlobeView = lazy(() => import('./GlobeView')) // three.js is heavy: load only when needed
type View = 'globe' | 'flat'
const KEY = 'gridflex.view'

// FE2: toggle between views, choice remembered. Selection is owned by App, so it survives a view switch.
interface Props {
  selectedId: string | null
  onSelect: (n: MapNode | null) => void
  move: Move | null
}

export function MapView({ selectedId, onSelect, move }: Props) {
  const [view, setView] = useState<View>(() => {
    try {
      return localStorage.getItem(KEY) === 'flat' ? 'flat' : 'globe'
    } catch {
      return 'globe'
    }
  })
  const pick = (v: View) => {
    setView(v)
    try {
      localStorage.setItem(KEY, v)
    } catch {
      /* storage unavailable: choice just isn't remembered */
    }
  }

  return (
    <>
      <div className="toggle" role="group" aria-label="Map view">
        {(['globe', 'flat'] as const).map((v) => (
          <button key={v} aria-pressed={view === v} onClick={() => pick(v)}>
            {v === 'globe' ? 'Globe' : 'Flat'}
          </button>
        ))}
      </div>
      {view === 'flat' ? (
        <FlatMap selectedId={selectedId} onSelect={onSelect} move={move} />
      ) : (
        <Suspense fallback={<p className="footnote">Loading globe…</p>}>
          <GlobeView selectedId={selectedId} onSelect={onSelect} move={move} />
        </Suspense>
      )}
    </>
  )
}

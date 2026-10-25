import { lazy, Suspense, useState } from 'react'
import { FlatMap } from './FlatMap'

const GlobeView = lazy(() => import('./GlobeView')) // three.js is heavy: load only when needed
type View = 'globe' | 'flat'
const KEY = 'gridflex.view'

// FE2: toggle between views, choice remembered. Selection/time will live in shared state later.
export function MapView() {
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
        <FlatMap />
      ) : (
        <Suspense fallback={<p className="footnote">Loading globe…</p>}>
          <GlobeView />
        </Suspense>
      )}
    </>
  )
}

import { useState } from 'react'
import { Dashboard } from './features/dashboard/Dashboard'
import { MapView } from './features/map/MapView'

export default function App() {
  const [lastGrid, setLastGrid] = useState<string | null>(null)
  return (
    <>
      <MapView onSelect={(n) => setLastGrid(n.grid)} />
      <Dashboard lastGrid={lastGrid} />
    </>
  )
}

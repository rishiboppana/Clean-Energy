import { useEffect, useState } from 'react'
import { ChatPanel } from './features/chat/ChatPanel'
import { Dashboard } from './features/dashboard/Dashboard'
import { NodeDetail } from './features/dashboard/NodeDetail'
import { MapView } from './features/map/MapView'
import type { MapNode, Move } from './features/map/nodes'

export default function App() {
  const [selected, setSelected] = useState<MapNode | null>(null)
  const [lastGrid, setLastGrid] = useState<string | null>(null) // dashboard's forecast chart keeps the last grid after deselect
  const [home, setHome] = useState('') // shared with the chat's "My location"
  const [move, setMove] = useState<Move | null>(null)

  const select = (n: MapNode | null) => {
    setSelected(n)
    if (n) setLastGrid(n.grid)
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setSelected(null) // FE9
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <MapView selectedId={selected?.id ?? null} onSelect={select} move={move} />
      {selected ? (
        <NodeDetail node={selected} isHome={home === selected.id} onSetHome={() => setHome(selected.id)} onBack={() => setSelected(null)} />
      ) : (
        <Dashboard lastGrid={lastGrid} />
      )}
      <ChatPanel home={home} setHome={setHome} onMove={setMove} />
    </>
  )
}

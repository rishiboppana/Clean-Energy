import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import Globe from 'react-globe.gl'
import type { GlobeMethods } from 'react-globe.gl'
import { NODES, nodeColor } from './nodes'
import type { MapNode, Move } from './nodes'
import { moonPhase } from './sky'
import { addSky, createEarthMaterial } from './sky3d'
import { otherCountries, states } from './states'

const polygons = [...otherCountries, ...states.features] // borders only; the satellite texture shows the land

// Nodes are unlit spheres with a white halo, so the red-to-green colors stay true in day and night.
const haloMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.BackSide })
const nodeMesh = (d: object) => {
  const n = d as MapNode
  const g = new THREE.Group()
  const r = 0.7 + 0.7 * n.share // FE6: size grows with absorbable MW
  g.add(new THREE.Mesh(new THREE.SphereGeometry(r, 24, 24), new THREE.MeshBasicMaterial({ color: nodeColor(n.share) })))
  g.add(new THREE.Mesh(new THREE.SphereGeometry(r * 1.2, 24, 24), haloMat))
  return g
}

// FE3: opens framed on the US. Google-Earth-like: satellite imagery, real day/night, atmosphere, stars.
export default function GlobeView({ selectedId, onSelect, move }: { selectedId: string | null; onSelect: (n: MapNode | null) => void; move: Move | null }) {
  const ref = useRef<GlobeMethods>(undefined)
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight })

  useEffect(() => {
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    ref.current?.pointOfView({ lat: 39, lng: -98, altitude: 1.8 })
  }, [])

  // Real sun and moon for the current time, refreshed every minute. `now` is the hook a time scrubber will set later.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(t)
  }, [])
  const earth = useMemo(() => createEarthMaterial(), [])
  const [ready, setReady] = useState(false) // node meshes need the globe instance to place them, so they are added once it exists
  const sky = useRef<ReturnType<typeof addSky>>(undefined)
  useEffect(() => {
    const g = ref.current
    if (!g) return
    sky.current = addSky(g, earth)
    setReady(true)
    return () => sky.current?.dispose()
  }, [earth])
  useEffect(() => sky.current?.update(now), [now])
  const moon = moonPhase(now)

  return (
    <>
    <Globe
      ref={ref}
      width={size.w}
      height={size.h}
      backgroundColor="#000000"
      backgroundImageUrl="/textures/night-sky.png"
      globeMaterial={earth}
      showAtmosphere
      atmosphereColor="#6fb2ff"
      atmosphereAltitude={0.18}
      polygonsData={polygons}
      polygonCapColor={() => 'rgba(0,0,0,0)'}
      polygonSideColor={() => 'rgba(0,0,0,0)'}
      polygonStrokeColor={() => 'rgba(255,255,255,0.18)'}
      customLayerData={ready ? NODES : []}
      customThreeObject={nodeMesh}
      customThreeObjectUpdate={(obj, d) => {
        const n = d as MapNode
        const c = ref.current?.getCoords(n.lat, n.lon, 0.01)
        if (c) obj.position.set(c.x, c.y, c.z)
      }}
      customLayerLabel={(d) => (d as MapNode).label}
      onCustomLayerClick={(d) => onSelect(d as MapNode)}
      onPolygonClick={() => onSelect(null)}
      onGlobeClick={() => onSelect(null)}
      arcsData={move ? [move] : []}
      arcStartLat={(d) => (d as Move).from.lat}
      arcStartLng={(d) => (d as Move).from.lon}
      arcEndLat={(d) => (d as Move).to.lat}
      arcEndLng={(d) => (d as Move).to.lon}
      arcColor={() => ['#ffd54a', '#ff7a00']}
      arcStroke={0.45}
      arcDashLength={0.04}
      arcDashGap={0.05}
      arcDashAnimateTime={1600}
      arcAltitudeAutoScale={0.35}
      ringsData={NODES.filter((n) => n.id === selectedId || n.id === move?.to.id)}
      ringLat={(d) => (d as MapNode).lat}
      ringLng={(d) => (d as MapNode).lon}
      ringColor={() => '#ffffff'}
      ringMaxRadius={2.5}
      ringPropagationSpeed={2}
      ringRepeatPeriod={1200}
    />
    <p className="sky-note">
      Sun and Moon shown at their real directions for {now.toISOString().slice(0, 16).replace('T', ' ')} UTC. Moon: {moon.name}, {Math.round(moon.illumination * 100)}% lit. Distances and sizes are not to scale. Imagery: NASA Blue Marble; clouds are a static image, not live weather.
    </p>
    </>
  )
}

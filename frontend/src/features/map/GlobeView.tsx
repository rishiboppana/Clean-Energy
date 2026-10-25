import { useEffect, useRef, useState } from 'react'
import Globe from 'react-globe.gl'
import type { GlobeMethods } from 'react-globe.gl'
import { NODES, nodeColor } from './nodes'
import type { MapNode } from './nodes'
import { otherCountries, states } from './states'

const token = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const land = token('--land')
const water = token('--water')
const edge = token('--land-stroke')
const polygons = [...otherCountries, ...states.features]

// 1x1 pixel in the water color used as the globe surface, so no texture file or license is involved
const SURFACE =
  'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1" fill="${water}"/></svg>`)

// FE3: opens framed on the US. FE24: light blue surface, light green land, state outlines, no texture.
export default function GlobeView({ onSelect }: { onSelect: (n: MapNode) => void }) {
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

  return (
    <Globe
      ref={ref}
      width={size.w}
      height={size.h}
      backgroundColor="rgba(0,0,0,0)"
      globeImageUrl={SURFACE}
      showAtmosphere
      polygonsData={polygons}
      polygonCapColor={() => land}
      polygonSideColor={() => 'rgba(0,0,0,0)'}
      polygonStrokeColor={() => edge}
      pointsData={NODES}
      pointLat={(d) => (d as MapNode).lat}
      pointLng={(d) => (d as MapNode).lon}
      pointColor={(d) => nodeColor((d as MapNode).share)}
      pointRadius={(d) => 0.4 + 0.4 * (d as MapNode).share}
      pointAltitude={0.02}
      onPointClick={(d) => onSelect(d as MapNode)}
      pointLabel={(d) => (d as MapNode).label}
    />
  )
}

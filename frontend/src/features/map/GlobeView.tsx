import { useEffect, useRef, useState } from 'react'
import Globe from 'react-globe.gl'
import type { GlobeMethods } from 'react-globe.gl'
import { NODES, nodeColor } from './nodes'
import type { MapNode } from './nodes'
import { states } from './states'

// 1x1 dark pixel used as the globe surface, so no texture file or license is involved
const SURFACE =
  'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1" fill="#0a1020"/></svg>')

// FE3: opens framed on the US. FE24: dark surface with state outlines, no texture.
export default function GlobeView() {
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
      polygonsData={states.features}
      polygonCapColor={() => '#141b30'}
      polygonSideColor={() => 'rgba(0,0,0,0)'}
      polygonStrokeColor={() => '#2a3558'}
      pointsData={NODES}
      pointLat={(d) => (d as MapNode).lat}
      pointLng={(d) => (d as MapNode).lon}
      pointColor={(d) => nodeColor((d as MapNode).share)}
      pointRadius={(d) => 0.25 + 0.5 * (d as MapNode).share}
      pointAltitude={0.02}
      pointLabel={(d) => (d as MapNode).label}
    />
  )
}

import type { GeometryCollection, Topology } from 'topojson-specification'
import { feature } from 'topojson-client'
import us from 'us-atlas/states-10m.json'

const topo = us as unknown as Topology<{ states: GeometryCollection }>
export const states = feature(topo, topo.objects.states)

import type { GeometryCollection, Topology } from 'topojson-specification'
import { feature } from 'topojson-client'
import us from 'us-atlas/states-10m.json'
import world from 'world-atlas/countries-110m.json'

const topo = us as unknown as Topology<{ states: GeometryCollection }>
export const states = feature(topo, topo.objects.states)

const w = world as unknown as Topology<{ countries: GeometryCollection }>
// Rest of the world for the globe; the US comes from the state-level data above.
export const otherCountries = feature(w, w.objects.countries).features.filter((c) => c.id !== '840')

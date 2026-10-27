// Real sun and moon positions (astronomy-engine, MIT). Pure functions of a Date, so a time scrubber can drive them later.
import * as A from 'astronomy-engine'

/** The point on Earth directly under the body (where it is overhead) at `date`. */
export function subpoint(body: 'Sun' | 'Moon', date: Date) {
  const t = A.MakeTime(date)
  const v = A.RotateVector(A.Rotation_EQJ_EQD(t), A.GeoVector(A.Body[body], t, true)) // equator of date, to match sidereal time
  const eq = A.EquatorFromVector(v)
  const lng = ((((eq.ra - A.SiderealTime(t)) * 15 + 540) % 360) + 360) % 360 - 180
  return { lat: eq.dec, lng }
}

/** Moon illumination 0..1 and a phase name, as seen from Earth. */
export function moonPhase(date: Date) {
  const deg = A.MoonPhase(date) // 0 new, 90 first quarter, 180 full, 270 last quarter
  const names = ['New moon', 'Waxing crescent', 'First quarter', 'Waxing gibbous', 'Full moon', 'Waning gibbous', 'Last quarter', 'Waning crescent']
  return { illumination: A.Illumination(A.Body.Moon, date).phase_fraction, name: names[Math.round(deg / 45) % 8] }
}

import type { Quality } from '../../data/hubs'

// A3: every number carries a quality label.
export function Badge({ q }: { q: Quality | 'assumption' }) {
  return <span className={`badge q-${q}`}>{q}</span>
}

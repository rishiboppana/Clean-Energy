export interface ChatReply {
  reply: string
  estimate: object | null
  job: Record<string, unknown> // the fields collected so far; the preview endpoint takes them as-is
  home_hub: string | null
  suggestions: string[]
  guarded: boolean // true when a guardrail answered without the LLM
  ended?: boolean // the user said that's everything after a placement away from home; the server deleted the conversation
}

export class ChatError extends Error {
  status: number
  constructor(status: number) {
    super(String(status))
    this.status = status
  }
}

// POST /v1/chat (proxied to the estimator service by vite.config.ts). Throws if the service or the LLM is unavailable.
export async function sendChat(sessionId: string, text: string, homeHub: string | null): Promise<ChatReply> {
  const r = await fetch('/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, text, home_hub: homeHub }),
  })
  if (!r.ok) throw new ChatError(r.status)
  return r.json()
}

export interface Preview {
  verdict: 'covered' | 'held' | 'not_covered' | 'infeasible' | 'data_unavailable'
  reasons: string[]
  best_slot?: { hub: string; grid: string; start_utc: string; end_utc: string; absorbed_mwh: { min: number; typ: number; max: number }; moved: boolean }
  latest_start_utc?: string
  basis: string // "simulated" until the surplus rule exists
}

async function post<T>(url: string, body: object): Promise<T> {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new ChatError(r.status)
  return r.json()
}

// POST /v1/jobs/preview: the scheduler's read-only verdict for this job from the user's hub. Commits nothing.
export const previewJob = (job: object, homeHub: string) => post<Preview>('/v1/jobs/preview', { ...job, home_hub: homeHub })

// POST /v1/chat/placement: tells the agent where the scheduler put the job; away from home it asks "is that everything?".
export const notifyPlacement = (sessionId: string, hub: string) =>
  post<{ reply: string; awaiting_end: boolean }>('/v1/chat/placement', { session_id: sessionId, hub })

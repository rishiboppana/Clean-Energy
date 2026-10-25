export interface ChatReply {
  reply: string
  estimate: unknown | null
  home_hub: string | null
}

// POST /v1/chat (proxied to the estimator service by vite.config.ts). Throws if the service or the LLM is unavailable.
export async function sendChat(sessionId: string, text: string, homeHub: string | null): Promise<ChatReply> {
  const r = await fetch('/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, text, home_hub: homeHub }),
  })
  if (!r.ok) throw new Error(String(r.status))
  return r.json()
}

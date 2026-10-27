import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { HUBS } from '../../data/hubs'
import { NODES } from '../map/nodes'
import type { Move } from '../map/nodes'
import { Badge } from '../dashboard/Badge'
import { ChatError, notifyPlacement, previewJob, sendChat } from './api'
import type { Preview } from './api'

interface Msg {
  who: 'user' | 'bot'
  text: string
  estimate?: boolean
  guarded?: boolean
}

const HELLO: Msg = {
  who: 'bot',
  text: "Tell me the job you want to run and where you are, for example: \"fine-tune a 7B model on 150 million tokens within 2 days, I'm in Dallas\".",
}

const EXAMPLES = [
  "Fine-tune a 7B model on 150 million tokens within 2 days, I'm in Dallas",
  "I need 64 GPU-hours of training done by tomorrow, I'm in Chicago",
  'LoRA fine-tune a 13B model on 50 million tokens in 3 days, Atlanta',
]

const byId = Object.fromEntries(NODES.map((n) => [n.id, n]))

const when = (iso: string) => {
  const d = new Date(iso)
  return `${d.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })} (${d.toISOString().slice(0, 16).replace('T', ' ')} UTC)`
}

// Ask the scheduler where the job runs, tell the map to draw the arrow, and say why in plain words. Everything here comes from the
// scheduler's verdict; surplus is simulated until the surplus rule exists, and the message says so.
function describe(p: Preview, home: string) {
  const note = ' Surplus is simulated. This is a preview, not a reservation.'
  const s = p.best_slot
  if (p.verdict === 'covered' && s) {
    const dest = byId[s.hub]
    const mwh = `${s.absorbed_mwh.typ.toFixed(3)} MWh (range ${s.absorbed_mwh.min.toFixed(3)} to ${s.absorbed_mwh.max.toFixed(3)})`
    const where = s.moved ? `move the job from ${home} to ${dest.name} (${s.grid})` : `run at ${home} (${s.grid})`
    return `Scheduler: ${where}, ${when(s.start_utc)} to ${when(s.end_utc)}. Surplus alone powers it, absorbing about ${mwh}.${note}`
  }
  if (p.verdict === 'held') return `Scheduler: no surplus window right now. It is held and re-checked each hour; latest start is ${when(p.latest_start_utc!)}.${note}`
  if (p.verdict === 'infeasible') return `Scheduler: this job cannot finish by the deadline even at ${home}. Try a later deadline.`
  if (p.verdict === 'data_unavailable') return `Scheduler: the surplus forecast is missing, so it would run at ${home} as normal load.${note}`
  return `Scheduler: no surplus window covers this job, so it runs at ${home} as normal load.${note}`
}

// FE10: right-hand chat with the job box. Numbers shown come from the estimator, never from the LLM.
export function ChatPanel({ home, setHome, onMove }: { home: string; setHome: (id: string) => void; onMove: (m: Move | null) => void }) {
  const [open, setOpen] = useState(true)
  const [msgs, setMsgs] = useState<Msg[]>([HELLO])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [chips, setChips] = useState(EXAMPLES)
  const session = useRef(crypto.randomUUID())
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [msgs, busy])

  function submit(e: FormEvent) {
    e.preventDefault()
    send(text)
  }

  async function send(raw: string) {
    const t = raw.trim()
    if (!t || busy) return
    setText('')
    setBusy(true)
    setMsgs((m) => [...m, { who: 'user', text: t }])
    try {
      const r = await sendChat(session.current, t, home || null)
      if (r.ended) { // the server deleted the conversation: wipe it here too and start a fresh session
        session.current = crypto.randomUUID()
        onMove(null)
        setMsgs([{ who: 'bot', text: r.reply }, HELLO])
        setChips(EXAMPLES)
        return
      }
      if (r.home_hub) setHome(r.home_hub)
      setMsgs((m) => [...m, { who: 'bot', text: r.reply, estimate: !!r.estimate, guarded: r.guarded }])
      setChips(r.suggestions)
      if (r.estimate) await schedule(r.job, r.home_hub)
      else onMove(null)
    } catch (err) {
      const limited = err instanceof ChatError && err.status === 429
      setMsgs((m) => [...m, {
        who: 'bot',
        guarded: true,
        text: limited
          ? "You've sent a lot of messages in the last hour. Please wait a bit, or start a new job."
          : 'The job box is unavailable right now (the estimator service or the LLM is down). Please try again shortly.',
      }])
      setChips([])
    } finally {
      setBusy(false)
    }
  }

  const say = (text: string) => setMsgs((m) => [...m, { who: 'bot', text }])

  async function schedule(job: Record<string, unknown>, homeId: string | null) {
    if (!homeId) {
      onMove(null)
      say('Pick your location (or tell me where you are) and I will ask the scheduler where this job would run.')
      return
    }
    try {
      const p = await previewJob(job, homeId)
      const slot = p.best_slot
      onMove(p.verdict === 'covered' && slot?.moved ? { from: byId[homeId], to: byId[slot.hub] } : null)
      say(describe(p, byId[homeId].name))
      if (p.verdict === 'covered' && slot) {
        const n = await notifyPlacement(session.current, slot.hub) // away from home the agent asks "is that everything?"
        if (n.awaiting_end) say(n.reply)
      }
    } catch {
      onMove(null)
      say('I could not reach the scheduler just now. The estimate above still stands.')
    }
  }

  function reset() {
    session.current = crypto.randomUUID()
    onMove(null)
    setMsgs([HELLO])
    setChips(EXAMPLES)
    setText('')
  }

  if (!open) {
    return <button className="chat-tab" onClick={() => setOpen(true)}>Job box</button>
  }

  return (
    <aside className="chat" aria-label="Job box chat">
      <header>
        <h2>Job box</h2>
        <span>
          <button onClick={reset} aria-label="Start a new job" title="Start a new job">↻</button>
          <button onClick={() => setOpen(false)} aria-label="Collapse chat">×</button>
        </span>
      </header>
      <label className="loc">
        My location
        <select value={home} onChange={(e) => setHome(e.target.value)}>
          <option value="">Not set</option>
          {HUBS.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
        </select>
      </label>
      <div className="msgs" aria-live="polite">
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.who}${m.guarded ? ' guard' : ''}`}>
            {m.text}
            {m.estimate && <div><Badge q="estimate" /></div>}
          </div>
        ))}
        {!busy && chips.length > 0 && (
          <div className="chips">
            {chips.map((c) => <button key={c} type="button" onClick={() => send(c)}>{c}</button>)}
          </div>
        )}
        {busy && <div className="msg bot typing" aria-label="Thinking"><i /><i /><i /></div>}
        <div ref={end} />
      </div>
      <form onSubmit={submit}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Describe your job and where you are…" autoFocus maxLength={2000} aria-label="Message" />
        <button disabled={busy || !text.trim()}>Send</button>
      </form>
      <p className="note">Your message is sent to a hosted LLM (Llama via Hugging Face) to read the job. All numbers come from the estimator and are estimates. This is not a reservation.</p>
    </aside>
  )
}

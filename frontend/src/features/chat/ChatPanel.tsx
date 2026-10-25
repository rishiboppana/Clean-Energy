import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { HUBS } from '../../data/hubs'
import { Badge } from '../dashboard/Badge'
import { ChatError, sendChat } from './api'

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

// FE10: right-hand chat with the job box. Numbers shown come from the estimator, never from the LLM.
export function ChatPanel() {
  const [open, setOpen] = useState(true)
  const [msgs, setMsgs] = useState<Msg[]>([HELLO])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [home, setHome] = useState('')
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
      if (r.home_hub) setHome(r.home_hub)
      setMsgs((m) => [...m, { who: 'bot', text: r.reply, estimate: !!r.estimate, guarded: r.guarded }])
      setChips(r.suggestions)
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

  function reset() {
    session.current = crypto.randomUUID()
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

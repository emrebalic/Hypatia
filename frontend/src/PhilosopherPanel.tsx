import { useState } from 'react'
import type { DebateFallacy, DebateMapEdge, DebateMapNode, MapSpeaker } from './ArgumentMap'

export type PhilosopherName = 'aristotle' | 'socrates' | 'hypatia' | 'kant' | 'marcus-aurelius' | 'epicurus'

export interface PhilosopherSegment {
  id: string
  speaker: string
  start: number
  end: number
  text: string
}

export interface PhilosopherGraph {
  speakers: MapSpeaker[]
  segments: PhilosopherSegment[]
  nodes: DebateMapNode[]
  edges: DebateMapEdge[]
  fallacies: DebateFallacy[]
}

export interface PhilosopherPoint {
  title: string
  text: string
  node_ids: string[]
}

export interface PhilosopherReply {
  philosopher: PhilosopherName
  summary: string
  points: PhilosopherPoint[]
}

interface PhilosopherPanelProps {
  result: PhilosopherGraph | null
  selectedNodeId: string | null
  onSelectNode: (nodeId: string) => void
}

const PHILOSOPHERS: { id: PhilosopherName; label: string; detail: string }[] = [
  { id: 'aristotle', label: 'Aristotle', detail: 'verdict from syllogistic structure' },
  { id: 'socrates', label: 'Socrates', detail: 'probing questions, no verdict' },
  { id: 'hypatia', label: 'Hypatia', detail: 'step-by-step proof check' },
  { id: 'kant', label: 'Kant', detail: 'could everyone live by that rule?' },
  { id: 'marcus-aurelius', label: 'Marcus Aurelius', detail: 'control what you can, calmly' },
  { id: 'epicurus', label: 'Epicurus', detail: 'which view brings less needless worry?' },
]

const HYPATIA_NOTE =
  'Her writings did not survive — this step-by-step check is inspired by the mathematical tradition she taught.'

async function readError(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json()
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string' && detail.trim() !== '') return detail
    }
    return `Request failed (${res.status} ${res.statusText}).`
  } catch {
    return `Request failed (${res.status} ${res.statusText}).`
  }
}

export default function PhilosopherPanel({ result, selectedNodeId, onSelectNode }: PhilosopherPanelProps) {
  const [philosopher, setPhilosopher] = useState<PhilosopherName>('aristotle')
  const [replies, setReplies] = useState<PhilosopherReply[]>([])
  const [followUpQuestion, setFollowUpQuestion] = useState<string | null>(null)
  const [followUp, setFollowUp] = useState('')
  const [followUpUsed, setFollowUpUsed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const nodesById = new Map((result?.nodes ?? []).map((node) => [node.id, node]))

  function choose(next: PhilosopherName) {
    if (next === philosopher) return
    setPhilosopher(next)
    setReplies([])
    setFollowUpQuestion(null)
    setFollowUp('')
    setFollowUpUsed(false)
    setError(null)
  }

  async function ask(userMessage?: string) {
    if (!result || loading) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/philosopher', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ philosopher, result, user_message: userMessage ?? null }),
      })
      if (!res.ok) {
        setError(await readError(res))
        return
      }
      const reply = (await res.json()) as PhilosopherReply
      if (userMessage !== undefined) {
        setFollowUpQuestion(userMessage)
        setReplies((prev) => [...prev, reply])
        setFollowUpUsed(true)
        setFollowUp('')
      } else {
        setReplies([reply])
        setFollowUpQuestion(null)
        setFollowUp('')
        setFollowUpUsed(false)
      }
    } catch {
      setError('Could not reach the API. Is the backend running on http://localhost:8000?')
    } finally {
      setLoading(false)
    }
  }

  function handleFollowUp() {
    if (followUp.trim() === '') {
      setError('Write a follow-up question first.')
      return
    }
    void ask(followUp.trim())
  }

  return (
    <div className="philosopher-panel">
      <div className="philosopher-choices" role="radiogroup" aria-label="Choose a philosopher">
        {PHILOSOPHERS.map((option) => (
          <label key={option.id} className={option.id === philosopher ? 'philosopher-choice philosopher-choice-active' : 'philosopher-choice'}>
            <input
              type="radio"
              name="philosopher"
              value={option.id}
              checked={option.id === philosopher}
              disabled={loading}
              onChange={() => choose(option.id)}
            />
            <span>
              <strong>{option.label}</strong>
              <small>{option.detail}</small>
            </span>
          </label>
        ))}
      </div>

      {philosopher === 'hypatia' && <p className="philosopher-note">{HYPATIA_NOTE}</p>}

      {!result ? (
        <p className="hint">Analyze a debate first — the philosopher judges the argument map above.</p>
      ) : (
        <button
          type="button"
          className="philosopher-ask"
          disabled={loading}
          onClick={() => void ask()}
        >
          {loading ? 'Asking…' : replies.length > 0 ? 'Ask again' : `Ask ${PHILOSOPHERS.find((option) => option.id === philosopher)?.label ?? ''}`}
        </button>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div aria-live="polite">
        {replies.map((reply, replyIndex) => (
          <article key={`${reply.philosopher}-${replyIndex}`} className="philosopher-reply">
            {replyIndex > 0 && followUpQuestion !== null && (
              <p className="philosopher-followup-q">
                <strong>You asked:</strong> {followUpQuestion}
              </p>
            )}
            <p className="philosopher-summary">{reply.summary}</p>
            <ol className="philosopher-points">
              {reply.points.map((point, pointIndex) => (
                <li key={`${replyIndex}-${pointIndex}`} className="philosopher-point">
                  {point.title.trim() !== '' && <strong>{point.title}</strong>}
                  <p>{point.text}</p>
                  <div className="node-chips">
                    {point.node_ids.map((nodeId) => {
                      const node = nodesById.get(nodeId)
                      const active = nodeId === selectedNodeId
                      return (
                        <button
                          key={nodeId}
                          type="button"
                          className={active ? 'node-chip node-chip-active' : 'node-chip'}
                          aria-pressed={active}
                          title={node ? `${node.type} — ${node.text}` : nodeId}
                          onClick={() => onSelectNode(nodeId)}
                        >
                          {nodeId}
                        </button>
                      )
                    })}
                  </div>
                </li>
              ))}
            </ol>
          </article>
        ))}
      </div>

      {result && replies.length === 1 && !followUpUsed && (
        <div className="philosopher-followup">
          <label htmlFor="philosopher-followup">Reply once — one follow-up per judgement</label>
          <textarea
            id="philosopher-followup"
            rows={2}
            value={followUp}
            disabled={loading}
            placeholder="e.g. What about the junior onboarding point?"
            onChange={(event) => setFollowUp(event.target.value)}
          />
          <button type="button" className="philosopher-ask" disabled={loading} onClick={handleFollowUp}>
            {loading ? 'Sending…' : 'Send follow-up'}
          </button>
        </div>
      )}
      {followUpUsed && <p className="hint">Follow-up used — ask again or pick another philosopher for a fresh judgement.</p>}
    </div>
  )
}

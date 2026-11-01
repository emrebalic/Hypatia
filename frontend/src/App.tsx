import { useRef, useState } from 'react'
import ArgumentMap, { type DebateFallacy, type DebateMapEdge, type DebateMapNode } from './ArgumentMap'
import FallacyPanel from './FallacyPanel'
import PhilosopherPanel from './PhilosopherPanel'
import LearnPanel, { type LearnOpenRequest } from './LearnPanel'
import './App.css'

interface Speaker {
  id: string
  label: string
}

interface Segment {
  id: string
  speaker: string
  start: number
  end: number
  text: string
}

interface DebateSummary {
  speakers: number
  segments: number
  nodes: number
  edges: number
  fallacies: number
}

interface AnalyzeResult {
  speakers: Speaker[]
  segments: Segment[]
  nodes: DebateMapNode[]
  edges: DebateMapEdge[]
  fallacies: DebateFallacy[]
}

type BusyKind = 'idle' | 'transcript' | 'analyze'
type StageStatus = 'idle' | 'active' | 'done' | 'error'
type StageId = 'transcript' | 'arguments' | 'fallacies' | 'verification'

const STAGES: { id: StageId; label: string; detail: string }[] = [
  { id: 'transcript', label: 'Transcript', detail: 'Upload + transcribe, or parse pasted text' },
  { id: 'arguments', label: 'Map arguments', detail: 'Analyst: premises → conclusion' },
  { id: 'fallacies', label: 'Flag fallacies', detail: 'FallacyHunter with exact quotes' },
  { id: 'verification', label: 'Verify', detail: 'Quote + timestamp checks' },
]

const IDLE_STAGES: Record<StageId, StageStatus> = {
  transcript: 'idle',
  arguments: 'idle',
  fallacies: 'idle',
  verification: 'idle',
}

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

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

export default function App() {
  const [transcriptText, setTranscriptText] = useState('')
  const [fileName, setFileName] = useState<string | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState<BusyKind>('idle')
  const [stages, setStages] = useState<Record<StageId, StageStatus>>({ ...IDLE_STAGES })
  const [statusLine, setStatusLine] = useState('No debate loaded yet. Upload audio or paste a transcript.')
  const [error, setError] = useState<string | null>(null)
  const [transcriptInfo, setTranscriptInfo] = useState<{ speakers: Speaker[]; segments: Segment[] } | null>(null)
  const [summary, setSummary] = useState<DebateSummary | null>(null)
  const [mapGraph, setMapGraph] = useState<{ nodes: DebateMapNode[]; edges: DebateMapEdge[] } | null>(null)
  const [fallacies, setFallacies] = useState<DebateFallacy[]>([])
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedFallacyId, setSelectedFallacyId] = useState<string | null>(null)
  const [learnTarget, setLearnTarget] = useState<LearnOpenRequest | null>(null)
  const [seekNotice, setSeekNotice] = useState<string | null>(null)
  // Monotonic version of the loaded result. Used as the PhilosopherPanel
  // key so the panel remounts exactly when a *new* result arrives — the
  // old count-based key collided whenever two debates had equal counts.
  const [resultVersion, setResultVersion] = useState(0)

  const busyLabel = busy === 'transcript' ? 'Working on the transcript…' : busy === 'analyze' ? 'Analyzing the debate…' : null

  function clearAnalysisState() {
    setSummary(null)
    setMapGraph(null)
    setFallacies([])
    setTranscriptInfo(null)
    setSelectedNodeId(null)
    setSelectedFallacyId(null)
    setSeekNotice(null)
  }

  function markStage(ids: StageId[], status: StageStatus) {
    setStages((prev) => {
      const next = { ...prev }
      for (const id of ids) next[id] = status
      return next
    })
  }

  function speakerLabel(speakerId: string): string {
    const known = transcriptInfo?.speakers.find((speaker) => speaker.id === speakerId)
    return known ? known.label : speakerId
  }

  function seekTo(seconds: number, description: string) {
    const when = formatTime(seconds)
    const audio = audioRef.current
    if (audio && audioUrl) {
      try {
        audio.currentTime = seconds
      } catch {
        /* ignore seek errors (e.g. metadata not loaded yet) */
      }
      void audio.play().catch(() => undefined)
      setSeekNotice(`Playing from ${when} — ${description}.`)
    } else {
      setSeekNotice(`This point starts at ${when} (${description}). Upload the audio to listen from here.`)
    }
  }

  function seekToNode(node: DebateMapNode) {
    setSelectedNodeId(node.id)
    const firstBadge = fallacies.find((fallacy) => fallacy.node_id === node.id) ?? null
    setSelectedFallacyId(firstBadge ? firstBadge.id : null)
    seekTo(node.start, speakerLabel(node.speaker))
  }

  function handleSelectFallacy(fallacy: DebateFallacy) {
    setSelectedFallacyId(fallacy.id)
    setSelectedNodeId(fallacy.node_id)
    setLearnTarget((prev) => ({ name: fallacy.name, nonce: (prev?.nonce ?? 0) + 1 }))
  }

  function handlePhilosopherNode(nodeId: string) {
    setSelectedNodeId(nodeId)
    const firstBadge = fallacies.find((fallacy) => fallacy.node_id === nodeId) ?? null
    setSelectedFallacyId(firstBadge ? firstBadge.id : null)
  }

  async function runAnalyze(speakers: Speaker[], segments: Segment[]) {
    setBusy('analyze')
    markStage(['arguments', 'fallacies', 'verification'], 'active')
    setStatusLine('Analyzing: mapping arguments, flagging fallacies, verifying quotes…')
    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speakers, segments }),
      })
      if (!res.ok) {
        markStage(['arguments', 'fallacies', 'verification'], 'error')
        setError(await readError(res))
        setStatusLine('Analysis failed. Fix the problem and try again.')
        return
      }
      const result = (await res.json()) as AnalyzeResult
      markStage(['arguments', 'fallacies', 'verification'], 'done')
      setResultVersion((version) => version + 1)
      setMapGraph({ nodes: result.nodes, edges: result.edges })
      setFallacies(result.fallacies ?? [])
      const fallacyList = result.fallacies ?? []
      setSummary({
        speakers: result.speakers.length,
        segments: result.segments.length,
        nodes: result.nodes.length,
        edges: result.edges.length,
        fallacies: fallacyList.length,
      })
      setStatusLine(
        `Done: ${result.nodes.length} argument nodes, ${result.edges.length} links, ${fallacyList.length} fallacy flags from ${result.segments.length} transcript segments.`,
      )
    } catch {
      markStage(['arguments', 'fallacies', 'verification'], 'error')
      setError('Could not reach the API. Is the backend running on http://localhost:8000?')
      setStatusLine('Analysis failed. Fix the problem and try again.')
    } finally {
      setBusy('idle')
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file) return
    if (busy !== 'idle') return
    setError(null)
    clearAnalysisState()
    setFileName(file.name)
    setStages({ ...IDLE_STAGES, transcript: 'active' })
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    setAudioUrl(URL.createObjectURL(file))
    setBusy('transcript')
    setStatusLine(`Uploading ${file.name} and transcribing…`)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/transcribe', { method: 'POST', body: form })
      if (!res.ok) {
        markStage(['transcript'], 'error')
        setError(await readError(res))
        setStatusLine('Transcription failed. Fix the problem and try again.')
        setBusy('idle')
        return
      }
      const body = (await res.json()) as { speakers: Speaker[]; segments: Segment[] }
      markStage(['transcript'], 'done')
      setTranscriptInfo(body)
      setStatusLine(`Transcript ready: ${body.segments.length} segments. Analyzing…`)
      await runAnalyze(body.speakers, body.segments)
    } catch {
      markStage(['transcript'], 'error')
      setError('Could not reach the API. Is the backend running on http://localhost:8000?')
      setStatusLine('Transcription failed. Fix the problem and try again.')
      setBusy('idle')
    }
  }

  async function handlePaste() {
    if (busy !== 'idle') return
    if (transcriptText.trim() === '') {
      setError('Paste transcript text first. Format: [MM:SS] Speaker: words, one turn per line.')
      return
    }
    setError(null)
    clearAnalysisState()
    setStages({ ...IDLE_STAGES, transcript: 'active' })
    setBusy('transcript')
    setStatusLine('Parsing pasted transcript…')
    try {
      const res = await fetch('/api/transcript', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: transcriptText }),
      })
      if (!res.ok) {
        markStage(['transcript'], 'error')
        setError(await readError(res))
        setStatusLine('Could not parse the pasted transcript. Check the format and try again.')
        setBusy('idle')
        return
      }
      const body = (await res.json()) as { speakers: Speaker[]; segments: Segment[] }
      markStage(['transcript'], 'done')
      setTranscriptInfo(body)
      setStatusLine(`Transcript ready: ${body.segments.length} segments. Analyzing…`)
      await runAnalyze(body.speakers, body.segments)
    } catch {
      markStage(['transcript'], 'error')
      setError('Could not reach the API. Is the backend running on http://localhost:8000?')
      setStatusLine('Could not parse the pasted transcript. Check the format and try again.')
      setBusy('idle')
    }
  }

  async function handleDemo() {
    if (busy !== 'idle') return
    setError(null)
    clearAnalysisState()
    setStages({ transcript: 'done', arguments: 'done', fallacies: 'done', verification: 'done' })
    setBusy('analyze')
    setStatusLine('Loading saved demo result…')
    try {
      const res = await fetch('/api/demo')
      if (!res.ok) {
        setStages({ transcript: 'idle', arguments: 'idle', fallacies: 'idle', verification: 'idle' })
        setError(await readError(res))
        setStatusLine('Demo load failed. Analyze a debate first to create the saved result.')
        setBusy('idle')
        return
      }
      const result = (await res.json()) as AnalyzeResult
      setResultVersion((version) => version + 1)
      setTranscriptInfo({ speakers: result.speakers, segments: result.segments })
      setMapGraph({ nodes: result.nodes, edges: result.edges })
      setFallacies(result.fallacies ?? [])
      const fallacyList = result.fallacies ?? []
      setSummary({
        speakers: result.speakers.length,
        segments: result.segments.length,
        nodes: result.nodes.length,
        edges: result.edges.length,
        fallacies: fallacyList.length,
      })
      setStatusLine(
        `Demo loaded instantly (no API calls): ${result.nodes.length} argument nodes, ${result.edges.length} links, ${fallacyList.length} fallacy flags from ${result.segments.length} transcript segments.`,
      )
    } catch {
      setError('Could not reach the API. Is the backend running on http://localhost:8000?')
      setStatusLine('Demo load failed. Analyze a debate first to create the saved result.')
    } finally {
      setBusy('idle')
    }
  }

  function resetAll() {
    if (busy !== 'idle') return
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    setAudioUrl(null)
    setFileName(null)
    setTranscriptText('')
    setError(null)
    clearAnalysisState()
    setResultVersion((version) => version + 1)
    setStages({ ...IDLE_STAGES })
    setStatusLine('No debate loaded yet. Upload audio or paste a transcript.')
  }

  const firstSegmentStart = transcriptInfo && transcriptInfo.segments.length > 0 ? transcriptInfo.segments[0].start : null

  const philosopherResult =
    mapGraph && transcriptInfo
      ? {
          speakers: transcriptInfo.speakers,
          segments: transcriptInfo.segments,
          nodes: mapGraph.nodes,
          edges: mapGraph.edges,
          fallacies,
        }
      : null
  const philosopherKey = `result-${resultVersion}`

  return (
    <div className="app">
      <header className="app-header">
        <h1>HYPATIA</h1>
        <p className="app-tagline">
          Debate X-Ray: map every argument, flag every fallacy, ask a philosopher.
        </p>
        <p className="app-note">
          Demo debates are non-political. No medical or mental-health advice.
        </p>
      </header>

      <LearnPanel openRequest={learnTarget} />

      <section className="intake" aria-label="Load a debate">
        <h2>Load a debate</h2>
        <div className="intake-grid">
          <div className="field">
            <label htmlFor="audio-upload">Upload audio or video</label>
            <input
              id="audio-upload"
              type="file"
              accept="audio/*,video/mp4,.mp3,.wav,.m4a,.mp4"
              disabled={busy !== 'idle'}
              onChange={(event) => void handleFile(event.target.files?.[0])}
            />
            <p className="hint">mp3, wav, m4a, or mp4. Clips up to 10 minutes; other formats convert with ffmpeg.</p>
            {fileName && (
              <p className="hint">
                File: <strong>{fileName}</strong>
              </p>
            )}
          </div>
          <div className="field">
            <label htmlFor="transcript-paste">Or paste a transcript</label>
            <textarea
              id="transcript-paste"
              rows={6}
              placeholder={'[00:00] Speaker 1: Remote work should be the default.\n[00:09] Speaker 2: I disagree…'}
              value={transcriptText}
              disabled={busy !== 'idle'}
              onChange={(event) => setTranscriptText(event.target.value)}
            />
            <div className="intake-actions">
              <button type="button" disabled={busy !== 'idle'} onClick={() => void handlePaste()}>
                {busy === 'idle' ? 'Analyze pasted transcript' : 'Working…'}
              </button>
              <button type="button" className="secondary" disabled={busy !== 'idle'} onClick={() => void handleDemo()}>
                Load demo instantly
              </button>
              <button type="button" className="secondary" disabled={busy !== 'idle'} onClick={resetAll}>
                Start over
              </button>
            </div>
            <p className="hint">Demo loads backend/data/last_result.json with no model calls — for recording the video.</p>
          </div>
        </div>

        <ol className="stages" aria-label="Pipeline stages" aria-live="polite">
          {STAGES.map((stage) => {
            const status = stages[stage.id]
            return (
              <li key={stage.id} className={`stage stage-${status}`}>
                <span className="stage-dot" aria-hidden="true">
                  {status === 'active' && <span className="spinner" />}
                  {status === 'done' && '✓'}
                  {status === 'error' && '!'}
                </span>
                <span className="stage-text">
                  <strong>
                    {stage.label}
                    {status === 'active' ? ' — working…' : status === 'done' ? ' — done' : status === 'error' ? ' — failed' : ''}
                  </strong>
                  <small>{stage.detail}</small>
                </span>
              </li>
            )
          })}
        </ol>
        <p className="status-line" role="status">
          {busyLabel ? `${busyLabel} ` : ''}{statusLine}
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>

      <main className="layout">
        <section className="column" aria-label="Media player">
          <h2>Player</h2>
          {!audioUrl && <p>Upload a debate or podcast episode to play it here.</p>}
          <audio
            ref={audioRef}
            controls
            preload={audioUrl ? 'metadata' : 'none'}
            className="player"
            src={audioUrl ?? undefined}
          />
          {seekNotice && (
            <p className="seek-notice" role="status">
              {seekNotice}
            </p>
          )}
          {transcriptInfo && (
            <p className="hint">
              {transcriptInfo.speakers.length} speaker{transcriptInfo.speakers.length === 1 ? '' : 's'} ·{' '}
              {transcriptInfo.segments.length} segments
              {firstSegmentStart !== null ? ` · starts ${formatTime(firstSegmentStart)}` : ''}
            </p>
          )}
        </section>
        <section className="column" aria-label="Argument map">
          <h2>Argument map</h2>
          {summary ? (
            <p>
              {summary.nodes} argument nodes, {summary.edges} links, {summary.fallacies} fallacy flags from{' '}
              {summary.segments} segments.
            </p>
          ) : (
            <p>Premises and conclusions appear here as a graph once a debate is analyzed.</p>
          )}
          {mapGraph ? (
            <>
              <ArgumentMap
                nodes={mapGraph.nodes}
                edges={mapGraph.edges}
                speakers={transcriptInfo?.speakers ?? []}
                fallacies={fallacies}
                selectedNodeId={selectedNodeId}
                onNodeSelect={seekToNode}
              />
              <p className="hint">Tip: click a node to seek the player to its timestamp.</p>
              <FallacyPanel
                fallacies={fallacies}
                nodes={mapGraph.nodes}
                speakerLabel={speakerLabel}
                selectedNodeId={selectedNodeId}
                selectedFallacyId={selectedFallacyId}
                onSelectFallacy={handleSelectFallacy}
                onSeekStart={seekTo}
              />
            </>
          ) : (
            <div className="map-placeholder">No debate loaded yet.</div>
          )}
        </section>
        <section className="column" aria-label="Philosopher panel">
          <h2>Philosopher</h2>
          <PhilosopherPanel
            key={philosopherKey}
            result={philosopherResult}
            selectedNodeId={selectedNodeId}
            onSelectNode={handlePhilosopherNode}
          />
        </section>
      </main>
    </div>
  )
}

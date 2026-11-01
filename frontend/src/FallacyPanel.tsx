import type { DebateFallacy, DebateMapNode } from './ArgumentMap'

export function formatFallacyTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

interface FallacyPanelProps {
  fallacies: DebateFallacy[]
  nodes: DebateMapNode[]
  speakerLabel: (speakerId: string) => string
  selectedNodeId: string | null
  selectedFallacyId: string | null
  onSelectFallacy: (fallacy: DebateFallacy) => void
  onSeekStart: (seconds: number, description: string) => void
}

export default function FallacyPanel({
  fallacies,
  nodes,
  speakerLabel,
  selectedNodeId,
  selectedFallacyId,
  onSelectFallacy,
  onSeekStart,
}: FallacyPanelProps) {
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  const selected =
    fallacies.find((fallacy) => fallacy.id === selectedFallacyId) ??
    (selectedNodeId !== null ? fallacies.find((fallacy) => fallacy.node_id === selectedNodeId) : undefined)

  if (fallacies.length === 0) {
    return (
      <div className="fallacy-panel">
        <h3>Fallacy flags (0)</h3>
        <p className="hint">No fallacies were flagged in this debate.</p>
      </div>
    )
  }

  return (
    <div className="fallacy-panel">
      <h3>Fallacy flags ({fallacies.length})</h3>
      <ul className="fallacy-list">
        {fallacies.map((fallacy) => {
          const unverified = fallacy.verified === false
          const onSelectedNode = selectedNodeId !== null && fallacy.node_id === selectedNodeId
          const isActive = selected?.id === fallacy.id
          const classes = [
            'fallacy-item',
            unverified ? 'fallacy-unverified' : '',
            onSelectedNode ? 'fallacy-on-selected-node' : '',
            isActive ? 'fallacy-selected' : '',
          ]
            .filter(Boolean)
            .join(' ')
          return (
            <li key={fallacy.id}>
              <button type="button" className={classes} aria-pressed={isActive} onClick={() => onSelectFallacy(fallacy)}>
                <span className="fallacy-item-status" aria-hidden="true">
                  {unverified ? '⚠️' : '✅'}
                </span>
                <span className="fallacy-item-name">{fallacy.name}</span>
                <span className="fallacy-item-meta">
                  {fallacy.node_id} · {formatFallacyTime(fallacy.start)}
                  {unverified ? ' · uncertain' : ''}
                </span>
              </button>
            </li>
          )
        })}
      </ul>

      {selected ? (
        <article className={selected.verified ? 'fallacy-detail' : 'fallacy-detail fallacy-unverified'} aria-live="polite">
          <p className="fallacy-status" role="status">
            {selected.verified ? '✅ verified' : '⚠️ uncertain — shown greyed, treat with caution'}
          </p>
          <h4>{selected.name}</h4>
          <blockquote className="fallacy-quote">“{selected.quote}”</blockquote>
          <p className="fallacy-explanation">{selected.explanation}</p>
          <p className="hint">
            {(() => {
              const node = nodesById.get(selected.node_id)
              if (!node) return `On ${selected.node_id} · ${formatFallacyTime(selected.start)}.`
              return `On ${node.type} ${node.id} (${speakerLabel(node.speaker)}) · ${formatFallacyTime(selected.start)}.`
            })()}
          </p>
          <button
            type="button"
            className="fallacy-play"
            onClick={() => onSeekStart(selected.start, `fallacy “${selected.name}”`)}
          >
            Play from this quote ({formatFallacyTime(selected.start)})
          </button>
        </article>
      ) : selectedNodeId !== null ? (
        <p className="hint">The selected node has no fallacy flags. Pick a flag above to see its quote and explanation.</p>
      ) : (
        <p className="hint">Pick a flag to see the exact quote and explanation.</p>
      )}
    </div>
  )
}

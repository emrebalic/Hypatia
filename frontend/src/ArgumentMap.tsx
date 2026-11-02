import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge as FlowEdge,
  type Node as FlowNode,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

export type ArgumentNodeType = 'claim' | 'premise' | 'conclusion' | 'rebuttal'
export type ArgumentRelation = 'supports' | 'attacks'

export interface DebateMapNode {
  id: string
  type: ArgumentNodeType
  speaker: string
  text: string
  quote: string
  start: number
  verified: boolean
  segment_ids?: string[]
}

export interface DebateFallacy {
  id: string
  node_id: string
  name: string
  explanation: string
  quote: string
  start: number
  verified: boolean
}

export interface DebateMapEdge {
  source: string
  target: string
  relation: ArgumentRelation
}

export interface MapSpeaker {
  id: string
  label: string
}

interface NodeStyle {
  background: string
  border: string
}

export const NODE_COLORS: Record<ArgumentNodeType, NodeStyle> = {
  claim: { background: '#ede5f6', border: '#5b3d99' },
  premise: { background: '#f5ecd4', border: '#b08d4f' },
  conclusion: { background: '#e2d2f2', border: '#38245e' },
  rebuttal: { background: '#f7e8ea', border: '#7c2d3e' },
}

export const EDGE_COLORS: Record<ArgumentRelation, string> = {
  supports: '#4a6b57',
  attacks: '#7c2d3e',
}

export const MAP_NODE_WIDTH = 230
export const MAP_NODE_HEIGHT = 190

const LAYER_H_GAP = 40
const LAYER_V_GAP = 70

export function formatMapTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

function nodeLabel(node: DebateMapNode, speakerLabel: string, badges: DebateFallacy[]) {
  const unverified = node.verified === false
  return (
    <div
      className={`${unverified ? 'arg-node arg-node-unverified' : 'arg-node'} arg-node-kind-${node.type}`}
      title={`Seek to ${formatMapTime(node.start)}`}
    >
      <span className={`arg-node-type arg-node-type-${node.type}`}>{node.type}</span>
      {unverified && (
        <span className="arg-node-flag" title="This item did not pass verification">
          uncertain
        </span>
      )}
      {badges.length > 0 && (
        <span className="arg-node-badges">
          {badges.map((fallacy) => (
            <span
              key={fallacy.id}
              className={fallacy.verified ? 'arg-node-badge' : 'arg-node-badge arg-node-badge-unverified'}
              title={fallacy.explanation}
            >
              Fallacy: {fallacy.name}
              {!fallacy.verified && ' (uncertain)'}
            </span>
          ))}
        </span>
      )}
      <span className="arg-node-text">{node.text}</span>
      <span className="arg-node-meta">
        {speakerLabel} · {formatMapTime(node.start)}
      </span>
    </div>
  )
}

/**
 * Pure transform: debate graph → layered React Flow nodes + edges.
 * Longest-path layering from roots; bounded relaxation keeps cycles finite.
 * Within each layer, nodes are reordered by the barycenter (average
 * neighbour position) heuristic in both directions, which pulls connected
 * nodes toward each other and reduces edge crossings versus id order.
 * Dependency-free so the frontend builds from package-lock.json alone.
 */
export function layoutDebateGraph(
  nodes: DebateMapNode[],
  edges: DebateMapEdge[],
  speakers: MapSpeaker[] = [],
  fallacies: DebateFallacy[] = [],
): { flowNodes: FlowNode[]; flowEdges: FlowEdge[] } {
  const known = new Set(nodes.map((node) => node.id))
  const labels = new Map(speakers.map((speaker) => [speaker.id, speaker.label]))
  const badgesByNode = new Map<string, DebateFallacy[]>()
  for (const fallacy of fallacies) {
    if (!known.has(fallacy.node_id)) continue
    const list = badgesByNode.get(fallacy.node_id)
    if (list) {
      list.push(fallacy)
    } else {
      badgesByNode.set(fallacy.node_id, [fallacy])
    }
  }
  const outgoing = new Map<string, string[]>()
  for (const node of nodes) {
    outgoing.set(node.id, [])
  }
  for (const edge of edges) {
    if (known.has(edge.source) && known.has(edge.target) && edge.source !== edge.target) {
      outgoing.get(edge.source)?.push(edge.target)
    }
  }

  const depth = new Map<string, number>(nodes.map((node) => [node.id, 0]))
  for (let pass = 0; pass < nodes.length; pass += 1) {
    let changed = false
    for (const node of nodes) {
      const next = (depth.get(node.id) ?? 0) + 1
      for (const target of outgoing.get(node.id) ?? []) {
        if (next > (depth.get(target) ?? 0)) {
          depth.set(target, next)
          changed = true
        }
      }
    }
    if (!changed) break
  }

  const layers = new Map<number, DebateMapNode[]>()
  for (const node of nodes) {
    const key = depth.get(node.id) ?? 0
    const layer = layers.get(key)
    if (layer) {
      layer.push(node)
    } else {
      layers.set(key, [node])
    }
  }

  // Barycenter ordering: sort each layer by the average position of its
  // neighbours in the adjacent layer, sweeping down then up a few times.
  // Ties (and neighbourless nodes) fall back to start time, then id, so
  // the layout stays deterministic.
  const incoming = new Map<string, string[]>(nodes.map((node) => [node.id, []]))
  for (const edge of edges) {
    if (known.has(edge.source) && known.has(edge.target) && edge.source !== edge.target) {
      incoming.get(edge.target)?.push(edge.source)
    }
  }
  const layerKeys = [...layers.keys()].sort((a, b) => a - b)
  for (const key of layerKeys) {
    layers.get(key)?.sort((a, b) => a.start - b.start || a.id.localeCompare(b.id))
  }
  const positionOf = new Map<string, number>()
  const refreshPositions = () => {
    positionOf.clear()
    for (const key of layerKeys) {
      ;(layers.get(key) ?? []).forEach((node, index) => positionOf.set(node.id, index))
    }
  }
  const barycenter = (ids: string[], fallback: number): number => {
    const positions = ids
      .map((id) => positionOf.get(id))
      .filter((value): value is number => value !== undefined)
    return positions.length > 0 ? positions.reduce((sum, v) => sum + v, 0) / positions.length : fallback
  }
  refreshPositions()
  for (let sweep = 0; sweep < 4; sweep += 1) {
    const sweeps: { keys: number[]; neighbours: Map<string, string[]> }[] = [
      { keys: layerKeys, neighbours: incoming },
      { keys: [...layerKeys].reverse(), neighbours: outgoing },
    ]
    for (const { keys, neighbours } of sweeps) {
      for (const key of keys) {
        const layer = layers.get(key) ?? []
        const sorted = layer
          .map((node, index) => ({ node, key: barycenter(neighbours.get(node.id) ?? [], index) }))
          .sort((a, b) => a.key - b.key || a.node.start - b.node.start || a.node.id.localeCompare(b.node.id))
          .map((entry) => entry.node)
        layers.set(key, sorted)
        refreshPositions()
      }
    }
  }

  const flowNodes: FlowNode[] = []
  for (const key of layerKeys) {
    const layer = layers.get(key) ?? []
    const rowWidth = layer.length * (MAP_NODE_WIDTH + LAYER_H_GAP) - LAYER_H_GAP
    layer.forEach((node, index) => {
      const colors = NODE_COLORS[node.type]
      const unverified = node.verified === false
      flowNodes.push({
        id: node.id,
        position: {
          x: -rowWidth / 2 + index * (MAP_NODE_WIDTH + LAYER_H_GAP),
          y: key * (MAP_NODE_HEIGHT + LAYER_V_GAP),
        },
        data: { label: nodeLabel(node, labels.get(node.speaker) ?? node.speaker, badgesByNode.get(node.id) ?? []) },
        style: {
          background: unverified ? '#ececec' : colors.background,
          border: unverified ? '2px solid #8a8a8a' : `2px solid ${colors.border}`,
          borderRadius: 10,
          width: MAP_NODE_WIDTH,
          fontSize: 12,
          opacity: unverified ? 0.75 : 1,
        },
      })
    })
  }

  const flowEdges: FlowEdge[] = edges
    .filter((edge) => known.has(edge.source) && known.has(edge.target))
    .map((edge, index) => {
      const color = EDGE_COLORS[edge.relation]
      return {
        id: `e-${edge.source}-${edge.target}-${index}`,
        source: edge.source,
        target: edge.target,
        label: edge.relation,
        style: { stroke: color, strokeWidth: 2 },
        labelStyle: { fill: color, fontSize: 11, fontWeight: 700 },
        labelBgStyle: { fill: '#fff' },
        markerEnd: { type: MarkerType.ArrowClosed, color },
      }
    })

  return { flowNodes, flowEdges }
}

interface ArgumentMapProps {
  nodes: DebateMapNode[]
  edges: DebateMapEdge[]
  speakers?: MapSpeaker[]
  fallacies?: DebateFallacy[]
  selectedNodeId?: string | null
  onNodeSelect?: (node: DebateMapNode) => void
}

export default function ArgumentMap({ nodes, edges, speakers = [], fallacies = [], selectedNodeId = null, onNodeSelect }: ArgumentMapProps) {
  const { flowNodes, flowEdges } = useMemo(
    () => layoutDebateGraph(nodes, edges, speakers, fallacies),
    [nodes, edges, speakers, fallacies],
  )
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [legendOpen, setLegendOpen] = useState(false)

  useEffect(() => {
    function onFullscreenChange() {
      setIsFullscreen(document.fullscreenElement !== null)
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
      } else {
        await wrapRef.current?.requestFullscreen()
      }
    } catch {
      /* ignore: fullscreen unavailable or denied */
    }
  }

  if (nodes.length === 0) {
    return <div className="argument-map-empty">No debate loaded yet.</div>
  }

  function handleNodeClick(_event: ReactMouseEvent, flowNode: FlowNode) {
    const selected = nodes.find((node) => node.id === flowNode.id)
    if (selected) {
      onNodeSelect?.(selected)
    }
  }

  const renderedNodes =
    selectedNodeId === null
      ? flowNodes
      : flowNodes.map((flowNode) => (flowNode.id === selectedNodeId ? { ...flowNode, selected: true } : flowNode))

  return (
    <div className="argument-map-block">
      <div className="argument-map-toolbar">
        <span className="map-fallacy-count" role="status">
          {fallacies.length === 0
            ? 'No fallacy flags on this map'
            : `${fallacies.length} fallacy flag${fallacies.length === 1 ? '' : 's'} on this map — look for the dark red “Fallacy:” badges on the cards`}
        </span>
        <button
          type="button"
          className="map-fullscreen-btn"
          onClick={() => void toggleFullscreen()}
          aria-pressed={isFullscreen}
        >
          {isFullscreen ? 'Exit full screen' : '⛶ Full screen'}
        </button>
      </div>
      <div className="argument-map-wrapper" ref={wrapRef}>
        <ReactFlow
          nodes={renderedNodes}
          edges={flowEdges}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.15}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <div className="argument-map-legend">
        <button
          type="button"
          className="legend-toggle"
          aria-expanded={legendOpen}
          aria-controls="map-legend-body"
          onClick={() => setLegendOpen((open) => !open)}
        >
          <span>How to read?</span>
          <span className={legendOpen ? 'legend-arrow legend-arrow-open' : 'legend-arrow'} aria-hidden="true">
            ⌄
          </span>
        </button>
        {legendOpen && (
          <div id="map-legend-body" className="legend-body">
        <span className="legend-chip">
          <span className="legend-rule legend-rule-claim" aria-hidden="true" />
          <strong>Claim</strong> — the main point someone asserts
        </span>
        <span className="legend-chip">
          <span className="legend-rule legend-rule-premise" aria-hidden="true" />
          <strong>Premise</strong> — a reason given to back a claim
        </span>
        <span className="legend-chip">
          <span className="legend-rule legend-rule-conclusion" aria-hidden="true" />
          <strong>Conclusion</strong> — what the reasons are meant to lead to
        </span>
        <span className="legend-chip">
          <span className="legend-rule legend-rule-rebuttal" aria-hidden="true" />
          <strong>Rebuttal</strong> — a counter-argument (dashed red edge)
        </span>
        <span className="legend-chip">
          <span className="legend-line" style={{ background: EDGE_COLORS.supports }} />
          <strong>supports</strong> — backs the next point
        </span>
        <span className="legend-chip">
          <span className="legend-line" style={{ background: EDGE_COLORS.attacks }} />
          <strong>attacks</strong> — pushes against the next point
        </span>
        <span className="legend-chip">
          <span className="arg-node-badge" aria-hidden="true">
            Fallacy
          </span>
          reasoning error
        </span>
        <span className="legend-chip">
          <span className="legend-grey" aria-hidden="true" />
          grey = uncertain
        </span>
          </div>
        )}
      </div>
    </div>
  )
}

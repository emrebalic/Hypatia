import { useMemo, type MouseEvent as ReactMouseEvent } from 'react'
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
  start: number
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
  claim: { background: '#e8f0fe', border: '#1f5fa8' },
  premise: { background: '#fef7e0', border: '#8a6d00' },
  conclusion: { background: '#f3e8fd', border: '#6a2fb3' },
  rebuttal: { background: '#fdecea', border: '#b3261e' },
}

export const EDGE_COLORS: Record<ArgumentRelation, string> = {
  supports: '#2e7d32',
  attacks: '#b3261e',
}

export const MAP_NODE_WIDTH = 230
export const MAP_NODE_HEIGHT = 150

const LAYER_H_GAP = 40
const LAYER_V_GAP = 70

export function formatMapTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

function nodeLabel(node: DebateMapNode, speakerLabel: string) {
  return (
    <div className="arg-node" title={`Seek to ${formatMapTime(node.start)}`}>
      <span className={`arg-node-type arg-node-type-${node.type}`}>{node.type}</span>
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
 * Dependency-free so the frontend builds from package-lock.json alone.
 */
export function layoutDebateGraph(
  nodes: DebateMapNode[],
  edges: DebateMapEdge[],
  speakers: MapSpeaker[] = [],
): { flowNodes: FlowNode[]; flowEdges: FlowEdge[] } {
  const known = new Set(nodes.map((node) => node.id))
  const labels = new Map(speakers.map((speaker) => [speaker.id, speaker.label]))
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

  const flowNodes: FlowNode[] = []
  for (const key of [...layers.keys()].sort((a, b) => a - b)) {
    const layer = (layers.get(key) ?? []).sort((a, b) => a.id.localeCompare(b.id))
    const rowWidth = layer.length * (MAP_NODE_WIDTH + LAYER_H_GAP) - LAYER_H_GAP
    layer.forEach((node, index) => {
      const colors = NODE_COLORS[node.type]
      flowNodes.push({
        id: node.id,
        position: {
          x: -rowWidth / 2 + index * (MAP_NODE_WIDTH + LAYER_H_GAP),
          y: key * (MAP_NODE_HEIGHT + LAYER_V_GAP),
        },
        data: { label: nodeLabel(node, labels.get(node.speaker) ?? node.speaker) },
        style: {
          background: colors.background,
          border: `2px solid ${colors.border}`,
          borderRadius: 8,
          width: MAP_NODE_WIDTH,
          fontSize: 12,
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
  selectedNodeId?: string | null
  onNodeSelect?: (node: DebateMapNode) => void
}

export default function ArgumentMap({ nodes, edges, speakers = [], selectedNodeId = null, onNodeSelect }: ArgumentMapProps) {
  const { flowNodes, flowEdges } = useMemo(() => layoutDebateGraph(nodes, edges, speakers), [nodes, edges, speakers])

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
    <div>
      <div className="argument-map-wrapper">
        <ReactFlow nodes={renderedNodes} edges={flowEdges} onNodeClick={handleNodeClick} fitView>
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <div className="argument-map-legend" aria-label="Map legend">
        <span>
          <span className="legend-swatch" style={{ background: NODE_COLORS.claim.background, borderColor: NODE_COLORS.claim.border }} />
          Claim
        </span>
        <span>
          <span className="legend-swatch" style={{ background: NODE_COLORS.premise.background, borderColor: NODE_COLORS.premise.border }} />
          Premise
        </span>
        <span>
          <span className="legend-swatch" style={{ background: NODE_COLORS.conclusion.background, borderColor: NODE_COLORS.conclusion.border }} />
          Conclusion
        </span>
        <span>
          <span className="legend-swatch" style={{ background: NODE_COLORS.rebuttal.background, borderColor: NODE_COLORS.rebuttal.border }} />
          Rebuttal
        </span>
        <span>
          <span className="legend-line" style={{ background: EDGE_COLORS.supports }} />
          supports
        </span>
        <span>
          <span className="legend-line" style={{ background: EDGE_COLORS.attacks }} />
          attacks
        </span>
      </div>
    </div>
  )
}

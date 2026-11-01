import type { ReactNode } from 'react'

export type StageStatus = 'idle' | 'active' | 'done' | 'error'
export type StageId = 'transcript' | 'arguments' | 'fallacies' | 'verification'

const STAGES: { id: StageId; label: string; detail: string; icon: ReactNode }[] = [
  {
    id: 'transcript',
    label: 'Transcript',
    detail: 'Listens and separates the speakers',
    icon: (
      <>
        <path className="flow-anim" d="M5 10v4" />
        <path className="flow-anim" d="M9 6v12" />
        <path className="flow-anim" d="M13 3v18" />
        <path className="flow-anim" d="M17 7v10" />
        <path className="flow-anim" d="M21 10v4" />
      </>
    ),
  },
  {
    id: 'arguments',
    label: 'Argument map',
    detail: 'Connects premises to conclusions',
    icon: (
      <>
        <path d="M12 7v4M12 11l-6 6M12 11l6 6" />
        <circle className="flow-anim" cx="12" cy="5" r="2.5" />
        <circle className="flow-anim" cx="6" cy="19" r="2.5" />
        <circle className="flow-anim" cx="18" cy="19" r="2.5" />
      </>
    ),
  },
  {
    id: 'fallacies',
    label: 'Fallacies',
    detail: 'Hunts for flaws, with exact quotes',
    icon: (
      <>
        <circle className="flow-anim" cx="10.5" cy="10.5" r="6.5" />
        <path d="M15.5 15.5 21 21" />
        <path d="M10.5 7.5v3.5M10.5 13.5v.01" />
      </>
    ),
  },
  {
    id: 'verification',
    label: 'Verification',
    detail: 'Checks every quote against the source',
    icon: (
      <>
        <path className="flow-anim" d="M12 2.5 20 6v6c0 4.7-3.2 8-8 9.5C7.2 20 4 16.700 4 12V6z" />
        <path d="m8.500 12 2.500 2.500 4.500-5" />
      </>
    ),
  },
]

function linkStatus(from: StageStatus, to: StageStatus): StageStatus {
  if (from === 'error' || to === 'error') return 'error'
  if (from === 'active' || to === 'active') return 'active'
  if (from === 'done' && to === 'done') return 'done'
  return 'idle'
}

const STATUS_TEXT: Record<StageStatus, string> = {
  idle: 'waiting',
  active: 'working',
  done: 'done',
  error: 'failed',
}

export default function PipelineFlow({ stages }: { stages: Record<StageId, StageStatus> }) {
  return (
    <ol className="flow" aria-label="Analysis progress" aria-live="polite">
      {STAGES.map((stage, index) => {
        const status = stages[stage.id]
        const next = STAGES[index + 1]
        return (
          <li key={stage.id} className={`flow-step flow-${status}`}>
            {next && <span className={`flow-link flow-link-${linkStatus(status, stages[next.id])}`} aria-hidden="true" />}
            <span className="flow-orb" aria-hidden="true">
              <svg className="flow-icon" viewBox="0 0 24 24">
                {stage.icon}
              </svg>
            </span>
            <strong className="flow-label">{stage.label}</strong>
            <small className="flow-detail">{stage.detail}</small>
            <span className="sr-only">{STATUS_TEXT[status]}</span>
          </li>
        )
      })}
    </ol>
  )
}

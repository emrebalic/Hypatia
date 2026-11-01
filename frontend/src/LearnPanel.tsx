import { useEffect, useState } from 'react'

interface PhilosopherCard {
  id: string
  name: string
  years: string
  role: string
  judge: boolean
  colors: string[]
  tagline: string
  summary: string
  method: string[]
  in_hypatia: string
  image: string
  fallback_image: string
}

interface FallacyCard {
  id: string
  name: string
  colors: string[]
  what: string
  example: string
  tip: string
  taxonomy_name: string
  image: string
  fallback_image: string
}

interface ContentBundle {
  philosophers: PhilosopherCard[]
  fallacies: FallacyCard[]
}

export interface LearnOpenRequest {
  name: string
  nonce: number
}

type LibraryTab = 'philosophers' | 'fallacies'

function CardImage({ src, fallback, alt }: { src: string; fallback: string; alt: string }) {
  const [current, setCurrent] = useState(src)
  useEffect(() => setCurrent(src), [src])
  return (
    <img
      className="learn-card-image"
      src={current}
      alt={alt}
      loading="lazy"
      onError={() => {
        if (current !== fallback) setCurrent(fallback)
      }}
    />
  )
}

export default function LearnPanel({ openRequest }: { openRequest: LearnOpenRequest | null }) {
  const [content, setContent] = useState<ContentBundle | null>(null)
  const [failed, setFailed] = useState(false)
  const [tab, setTab] = useState<LibraryTab>('philosophers')
  const [openFallacyId, setOpenFallacyId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/content')
      .then(async (res) => {
        if (!res.ok) throw new Error(`content failed: ${res.status}`)
        const body = (await res.json()) as ContentBundle
        if (!cancelled) setContent(body)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!openRequest || !content) return
    const card = content.fallacies.find((fallacy) => fallacy.taxonomy_name === openRequest.name)
    if (!card) return
    setTab('fallacies')
    setOpenFallacyId(card.id)
    requestAnimationFrame(() => {
      document.getElementById(`learn-fallacy-${card.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }, [openRequest, content])

  if (failed) {
    return (
      <section className="library" aria-label="Library">
        <p className="hint">Library is unavailable (could not load /api/content).</p>
      </section>
    )
  }

  if (!content) {
    return (
      <section className="library" aria-label="Library">
        <p className="hint">Loading the library…</p>
      </section>
    )
  }

  return (
    <section className="library" aria-label="Library">
      <div className="library-head">
        <h2>The Library</h2>
        <p>Six ways of judging, twenty ways of going wrong.</p>
      </div>
      <div className="library-tabs" role="tablist" aria-label="Library sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'philosophers'}
          className={tab === 'philosophers' ? 'library-tab library-tab-active' : 'library-tab'}
          onClick={() => setTab('philosophers')}
        >
          Philosophers
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'fallacies'}
          className={tab === 'fallacies' ? 'library-tab library-tab-active' : 'library-tab'}
          onClick={() => setTab('fallacies')}
        >
          Fallacies
        </button>
      </div>

      {tab === 'philosophers' && (
        <div className="learn-grid" role="tabpanel" aria-label="Philosophers">
          {content.philosophers.map((philosopher) => (
            <details key={philosopher.id} className="learn-card">
              <summary className="learn-card-summary">
                <CardImage src={philosopher.image} fallback={philosopher.fallback_image} alt="" />
                <span className="learn-card-title">
                  <span className="learn-card-name">{philosopher.name}</span>
                  <small>
                    {philosopher.years} · {philosopher.role}
                  </small>
                  <span className="learn-card-tagline">{philosopher.tagline}</span>
                </span>
                {philosopher.judge && <span className="learn-judge-chip">Judge</span>}
              </summary>
              <div className="learn-card-body">
                <p>{philosopher.summary}</p>
                <p className="learn-method-label">Method</p>
                <ul>
                  {philosopher.method.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
                <p className="learn-in-hypatia">{philosopher.in_hypatia}</p>
              </div>
            </details>
          ))}
        </div>
      )}

      {tab === 'fallacies' && (
        <div className="learn-grid" role="tabpanel" aria-label="Fallacies">
          {content.fallacies.map((fallacy) => (
            <details
              key={fallacy.id}
              id={`learn-fallacy-${fallacy.id}`}
              className="learn-card"
              open={openFallacyId === fallacy.id}
              onToggle={(event) => {
                if ((event.target as HTMLDetailsElement).open) setOpenFallacyId(fallacy.id)
              }}
            >
              <summary className="learn-card-summary">
                <CardImage src={fallacy.image} fallback={fallacy.fallback_image} alt="" />
                <span className="learn-card-title">
                  <span className="learn-card-name">{fallacy.name}</span>
                  <span className="learn-card-tagline">{fallacy.what}</span>
                </span>
              </summary>
              <div className="learn-card-body">
                <p className="learn-example-label">Example</p>
                <p className="learn-example">{fallacy.example}</p>
                <p className="learn-example-label">How to answer it</p>
                <p>{fallacy.tip}</p>
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  )
}

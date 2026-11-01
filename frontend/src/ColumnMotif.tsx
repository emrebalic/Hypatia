interface ColumnMotifProps {
  mirrored?: boolean
}

/** Engraved Ionic column in the site duotone: aubergine ink, gold capital. */
export default function ColumnMotif({ mirrored = false }: ColumnMotifProps) {
  return (
    <svg
      className={mirrored ? 'column-motif column-motif-mirrored' : 'column-motif'}
      viewBox="0 0 28 76"
      aria-hidden="true"
      focusable="false"
    >
      {/* capital: gold abacus + volutes */}
      <g className="cm-gold" fill="none" strokeLinecap="round">
        <line x1="3" y1="4" x2="25" y2="4" />
        <path d="M5 10c-2.4 0-3.4-3.2-1.6-4.8C5 3.8 7 4.8 6.6 6.6" />
        <path d="M23 10c2.4 0 3.4-3.2 1.6-4.8C23 3.8 21 4.8 21.4 6.6" />
      </g>
      <line className="cm-lilac" x1="4" y1="12" x2="24" y2="12" />
      {/* fluted shaft */}
      <g className="cm-ink" strokeLinecap="round">
        <line x1="7" y1="16" x2="7" y2="62" />
        <line x1="11" y1="16" x2="11" y2="62" />
        <line x1="14" y1="16" x2="14" y2="62" />
        <line x1="17" y1="16" x2="17" y2="62" />
        <line x1="21" y1="16" x2="21" y2="62" />
      </g>
      {/* base + stepped plinth */}
      <g className="cm-ink" strokeLinecap="round">
        <line x1="5" y1="66" x2="23" y2="66" />
        <line x1="4" y1="70" x2="24" y2="70" />
        <line className="cm-gold" x1="3" y1="74" x2="25" y2="74" />
      </g>
    </svg>
  )
}

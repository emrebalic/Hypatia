import './App.css'

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Hypatia — Debate X-Ray</h1>
        <p className="app-note">
          Demo debates are non-political. No medical or mental-health advice.
        </p>
      </header>
      <main className="layout">
        <section className="column" aria-label="Media player">
          <h2>Player</h2>
          <p>Upload a debate or podcast episode to play it here.</p>
          <audio controls preload="none" className="player" />
        </section>
        <section className="column" aria-label="Argument map">
          <h2>Argument map</h2>
          <p>
            Premises and conclusions appear here as a graph (React Flow canvas
            lands here in task 13).
          </p>
          <div className="map-placeholder">No debate loaded yet.</div>
        </section>
        <section className="column" aria-label="Philosopher panel">
          <h2>Philosopher</h2>
          <p>Pick a judge: Aristotle, Socrates, or Hypatia.</p>
          <ul className="philosopher-list">
            <li>Aristotle — verdict from syllogistic structure</li>
            <li>Socrates — probing questions, no verdict</li>
            <li>Hypatia — step-by-step proof check</li>
          </ul>
        </section>
      </main>
    </div>
  )
}

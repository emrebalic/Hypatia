# Hypatia — Debate X-Ray with Philosopher Judges

Meta Global AI Developer Hackathon · Indie track · Theme: **Build for Your World**
Submission deadline: Nov 4, 9:00 PM ET. Internal feature freeze: **Nov 3, 12:00 Turkey time**.

## One-line pitch
Upload a debate or podcast. Hypatia transcribes it, maps every argument (premises → conclusion,
with clickable timestamps), flags logical fallacies, verifies its own claims, and lets you ask a
philosopher (Aristotle, Socrates, Hypatia) who is right — each judging with their *own* method.

## Why it is not a "basic RAG" or "simple education chatbot"
- Multi-agent pipeline with a **verifier agent** that checks the other agents' output.
- Output is a **structured argument graph** tied to timestamps in the media, not a chat.
- Philosopher agents apply a **method**, not a persona: Aristotle uses his theory of fallacies
  (Sophistical Refutations) and syllogistic structure; Socrates refuses to give a verdict and
  instead asks each side the question that exposes their weakest premise; Hypatia, a teacher of
  mathematics and astronomy, tests each side like a geometric proof: she states the definitions and
  assumptions it depends on, walks the steps, and marks exactly where the demonstration holds or breaks.
  None of her writings survive, so this method is inspired by the mathematical tradition she taught.
  Her prompt and panel say so, and she is never given invented quotes.

## Meta models used (required — judged at 25%)
All calls go through Meta Model API (OpenAI-compatible, base URL `https://api.meta.ai/v1`).
Model IDs MUST be read from env vars. Verified endpoints and shapes are in `NOTES.md`.
Transcription takes WAV only, up to 10 minutes; other formats are converted with ffmpeg first.
| Step | Agent | Model (env var) |
|---|---|---|
| Speech → text with speakers + timestamps | Transcriber | `META_TRANSCRIBE_MODEL` (Muse Voice Transcribe) |
| Claims / premises / conclusions → JSON graph | Analyst | `META_TEXT_MODEL` (Muse Spark) |
| Fallacy detection with quote + timestamp | FallacyHunter | `META_TEXT_MODEL` |
| Check every quote and label against transcript | Verifier | `META_TEXT_MODEL` + tool calling |
| Verdict / questions | Philosopher | `META_TEXT_MODEL` (optional: open-weights via `PHILOSOPHER_BASE_URL`) |

## MVP user flow (this is what the demo video shows)
1. User uploads an audio/video file (mp3, wav, m4a, mp4) **or** pastes a transcript (fallback).
2. Left panel: media player. Middle: argument map (React Flow). Right: philosopher panel.
3. Map nodes: Claim, Premise, Conclusion, Rebuttal. Edges: supports / attacks.
   Each node shows speaker + timestamp; clicking it seeks the player to that second.
4. Fallacy badges on nodes (e.g. "Straw man", "Ad hominem") with a short explanation and the
   exact quote. Verifier status per item: ✅ verified, ⚠️ uncertain (shown, greyed).
5. Philosopher panel: user picks Aristotle, Socrates or Hypatia → gets a verdict (Aristotle), probing
   questions (Socrates) or a step-by-step proof check (Hypatia), each point linked to map nodes.
   User can reply once; philosopher answers.

## Data contract (single source of truth: `backend/app/schemas.py`, pydantic)
```json
{
  "speakers": [{"id": "S1", "label": "Speaker 1"}],
  "segments": [{"id": "seg_1", "speaker": "S1", "start": 12.4, "end": 19.0, "text": "..."}],
  "nodes": [{"id": "n1", "type": "claim|premise|conclusion|rebuttal", "speaker": "S1",
             "text": "...", "quote": "exact words", "start": 12.4, "segment_ids": ["seg_1"],
             "verified": true}],
  "edges": [{"source": "n2", "target": "n1", "relation": "supports|attacks"}],
  "fallacies": [{"id": "f1", "node_id": "n3", "name": "Straw man", "explanation": "...",
                 "quote": "exact words", "start": 40.2, "verified": true}]
}
```
Rules: every `quote` must appear verbatim (case/whitespace-insensitive) in the transcript;
every `start` must fall inside its segment. The Verifier enforces this deterministically first,
then uses the model only for semantic checks.

## Out of scope (do NOT build)
- Downloading from YouTube or any site (copyright/ToS risk → disqualification).
- User accounts, databases, payments, deployment pipelines.
- Political topics: the demo uses a non-political debate. Add a visible note in the UI.
- Medical / mental-health advice of any kind.
- Image generation (stretch only, after everything else works).

## Stack
- Backend: Python 3.12, FastAPI, `openai` SDK pointed at Meta base URL, pydantic, pytest.
- Frontend: React + Vite + TypeScript, `@xyflow/react` (React Flow).
- OS: Windows. Scripts are PowerShell (`scripts/*.ps1`). No `make`, no bash-only commands.

## Definition of done
`powershell -File scripts/check.ps1` exits 0. It runs backend tests (offline, LLM mocked) and
the frontend production build. Plus: README with setup, architecture diagram (mermaid), what was
built during the hackathon, and which Meta models are used where.

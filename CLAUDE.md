# CLAUDE.md — Hypatia (handoff notes)

Read this first, then `SPEC.md` (source of truth), `AGENTS.md` (working rules), `TASKS.md` (ordered
task list) and `NOTES.md` (progress log). Follow AGENTS.md exactly; it applies to you too.

## What this is
Hypatia is Emre Baliç's entry to the **Meta Global AI Developer Hackathon** (run with Cerebral Valley,
virtual). Indie Developer track, solo. Theme: **Build for Your World**.
Product: upload a debate/podcast → transcript with speakers + timestamps → argument map
(premises/conclusions/rebuttals, clickable timestamps) → fallacy badges → verifier agent checks every
quote/label → user asks a philosopher (Aristotle gives a verdict, Socrates asks probing questions, Hypatia checks the proof),
each using their own *method*, not a persona.

## Hard deadlines (Turkey time, UTC+3)
- Official submission: **Thu Nov 5, 05:00** (= Nov 4, 9:00 PM ET). Late submissions not accepted.
- Emre is at another hackathon all day **Nov 4** → real deadline is **Nov 3 evening**.
- Feature freeze: **Nov 3, 12:00**. After that only bug fixes, README, demo prep.
- Emre has very little time; he checks in ~15 min twice a day. Work autonomously, keep commits small,
  write anything he must decide in `NOTES.md` under `## Blocked`.

## Hackathon rules that constrain the code (from the official participant guide)
- Repo must be **public** (github.com/emrebalic/Hypatia). Never commit secrets; key lives only in
  `backend/.env` (gitignored).
- Only work built during the hackathon counts; README must have a "Built during the hackathon" section.
- Submission needs a **3-minute demo video**, public repo link, live product.
- Project must use Meta models via Meta Model API and/or Meta open-weights models.
- Banned / disqualifying: basic RAG apps, simple image analyzers, simple "AI for education" chatbots,
  medical/mental-health advice, personality analyzers, sports, **anything political or about war**,
  using content you don't have rights to. → **No YouTube/site downloading.** Demo uses
  `fixtures/sample_transcript.txt` (non-political, remote-work debate) recorded by Emre himself.
- Judging (equal weights, 0–10): Impact · Use of Meta AI tooling · Technical depth · Demo.
  Bonus prizes worth aiming at: Best Agentic Use-Case, Best Build on Meta Open Weight Models
  (Muse Glimmer / Muse Spark Open via Modal or Baseten), Most Viral (X post).

## Meta Model API facts (verify in docs before relying on them)
- OpenAI-SDK compatible, base URL `https://api.meta.ai/v1`, key in `META_API_KEY`.
- Models available for the hackathon: Muse Spark series, Muse Wonder, Muse Image,
  Muse Voice Transcribe, SAM 3.1 (API); Muse Glimmer, Muse Spark Open (open weights); Muse Code (CLI agent).
- Model IDs and the transcription endpoint are verified and recorded in NOTES.md ("Verified API facts").
  Model IDs come from env vars only.
- Standard pricing (Muse Spark): ~$1.25 / M input, ~$4.25 / M output. Emre has **$150 credit**,
  spend limit set to ~$140. Keep live calls rare; unit tests are offline with mocked `meta_client`.
- Baseten model id for the hackathon: `meta-models/muse-spark-open-1026` (not the docs' default).

## Environment
- Emre's machine: **Windows**, PowerShell, VS Code. Repo at `C:\Users\emreb\projects\Hypatia`.
- No bash-only syntax in scripts. Use `scripts/*.ps1`.
- `scripts/run-loop.ps1` = overnight Muse Code headless loop. The agent has file tools only (the Windows
  sandbox shell does not work on this machine, see NOTES.md); the script runs `scripts/check.ps1`, feeds
  failures back and commits. `scripts/setup.ps1` = one-time setup (tool check, first commit, push).
- Python 3.12 (`py -3.12`); 3.11 is not installed.

## Current state (Nov 1)
- Only planning files exist: SPEC, AGENTS, TASKS, NOTES, fixtures, scripts. **No code yet.**
- Start at TASKS.md task 1. Phases target: P1 Nov 1 night · P2 Nov 2 morning · P3 Nov 2 evening ·
  P4 Nov 2 night · P5 before Nov 3 12:00.
- If time gets tight, cut in this order: Kant/stretch → Socrates follow-up → Hypatia → audio upload (keep the
  pasted-transcript path) . Never cut: argument map, verifier, Aristotle, demo mode.

## Decisions already made (don't relitigate)
- Name: Hypatia (was "Agora" in early drafts).
- Stack: FastAPI + pydantic + pytest / React + Vite + TS + @xyflow/react.
- Pasted transcript is the fallback input and the demo path; audio upload uses Muse Voice Transcribe.
- Philosophers for MVP: Aristotle, Socrates, Hypatia (geometric proof check; her writings did not survive,
  so never invent quotes for her).

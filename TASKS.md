# Tasks (do in order; tick when check.ps1 passes)

## Phase 1 — Skeleton (target: Nov 1 night)
- [x] 1. Backend skeleton: `backend/app/main.py` (FastAPI, `/health`), `backend/requirements.txt` (fastapi, uvicorn, pydantic, openai, httpx, python-multipart, python-dotenv, pytest), `backend/.env.example` (META_BASE_URL=https://api.meta.ai/v1, META_API_KEY=, META_TEXT_MODEL=muse-spark-1.3, META_TRANSCRIBE_MODEL=muse-voice-transcribe-1.0), pytest setup in `backend/tests/` with one passing test.
- [x] 2. `scripts/check.ps1`: creates/uses `backend/.venv`, installs requirements, runs pytest; then `npm ci` (or `npm install` on first run) and `npm run build` in `frontend/`. Exit non-zero on any failure. (Done during setup.)
- [x] 3. `backend/app/schemas.py`: pydantic models exactly matching the data contract in SPEC.md + tests using `fixtures/sample_debate.json`.
- [x] 4. `backend/app/meta_client.py`: thin wrapper (chat JSON call + transcription call via httpx) reading env vars; follow the shapes in NOTES.md "Verified API facts". Tests mock it.
- [x] 5. Frontend skeleton: Vite + React + TS, three-column layout (player / map / philosopher), builds cleanly.

## Phase 2 — Core pipeline (target: Nov 2 morning)
- [x] 6. `POST /api/transcribe`: accepts upload; converts non-WAV input to the required WAV with ffmpeg (clear 400 error if ffmpeg is missing); rejects audio over 10 minutes with a clear message; maps `turns` to `segments` + `speakers` (ms to seconds). Also accept `POST /api/transcript` with pasted text in the format of `fixtures/sample_transcript.txt` (fallback path, parses timestamps + speakers without any model call).
- [x] 7. Analyst agent: transcript → nodes + edges (JSON), prompt in `backend/app/prompts/analyst.md`. Test with canned reply from `fixtures/`.
- [x] 8. Deterministic verifier: every quote appears in transcript, every timestamp inside its segment; failing items get `verified=false`. Tests with deliberately broken canned replies.
- [x] 9. FallacyHunter agent: adds `fallacies` (name, explanation, quote, start). Prompt in `prompts/fallacy.md`. Runs through the deterministic verifier.
- [x] 10. Semantic verifier agent: for items passing step 8, asks the model "does this quote actually support this label?" → keeps or downgrades to `verified=false`.
- [x] 11. `POST /api/analyze`: runs Analyst → FallacyHunter → Verifiers, returns full contract JSON. Saves result to `backend/data/last_result.json` for fast demo reloads.

## Phase 3 — UI (target: Nov 2 evening)
- [x] 12. Upload + transcript paste screen; loading states per pipeline stage.
- [x] 13. Argument map with @xyflow/react: node colours per type, supports=green / attacks=red edges, auto-layout (dagre or elk).
- [x] 14. Click node → media player seeks to `start`. Speaker + timestamp on each node.
- [x] 15. Fallacy badges + side detail card with quote and explanation; unverified items greyed with ⚠️.

## Phase 4 — Philosophers (target: Nov 2 night)
- [x] 16. `POST /api/philosopher` {philosopher: "aristotle"|"socrates"|"hypatia", result, user_message?}. Prompts in `prompts/aristotle.md`, `prompts/socrates.md`, `prompts/hypatia.md` (minimal placeholder until task 24). Every point must reference node ids.
- [x] 17. Aristotle: verdict on who argued better, using syllogistic structure + his fallacy categories; references node ids. Socrates: no verdict, 2–3 probing questions per side targeting the weakest premise.
- [x] 24. Hypatia: for each side, list the definitions and assumptions its argument depends on, walk the steps in order, and mark each step `holds` or `breaks` with the reason and node ids. No overall winner; ends with what both sides have actually established. Write `prompts/hypatia.md`, with tests on canned replies. Never attribute quotes or writings to her; none survive.
- [x] 18. Philosopher panel UI: choose philosopher (Aristotle, Socrates, Hypatia), show response with clickable node references (highlight node on map), one follow-up reply from the user. Hypatia's panel shows a short note: her writings did not survive, and this method is inspired by the mathematical tradition she taught.

## Phase 5 — Polish (target: Nov 3 before 12:00 TR)
- [x] 19. "Demo mode": load `backend/data/last_result.json` instantly (no API calls) for recording the video.
- [x] 20. README: pitch, screenshots placeholder, mermaid architecture, which Meta model does what, setup steps for Windows, and a section "Built during the hackathon".
- [x] 21. Write a live smoke test in `backend/tests/live/` (RUN_LIVE=1): one short transcript through the full pipeline. Writing it completes the task; Emre runs it.

## Stretch (only if all above are ticked)
- [ ] 22. Third philosopher: Kant (universalisability test).
- [ ] 23. Philosopher agents on open-weights model via `PHILOSOPHER_BASE_URL` (Modal/Baseten) for the Open Weights bonus.

## Phase 6 — Learn & delight (from docs/LEARN_TASKS.md; after the core demo works)
- [ ] 25. Learn panel UI: a "Learn" tab/drawer listing philosopher cards (from `philosophers.json`) and
  fallacy cards (from `fallacies.json`). Each card: image (`image`, falling back to `fallback_image` on
  load error), name, one-line tagline, expandable summary/method/example/tip. Clicking a fallacy badge
  on the map opens its card (match on `taxonomy_name` == fallacy `name`). Warm, soft styling using each
  card's `colors`. Serve the JSON via `GET /api/content` (static, no model call). Add tests.
- [x] 26. `scripts/generate_images.py`: one-off generator using **Muse Image** through Meta Model API.
  First read https://dev.meta.ai/docs (Muse Image page) and record the exact endpoint, model id and
  parameters in NOTES.md — do not guess. Read every `image_prompt` from both JSON files, request a
  square image, save to the card's `image` path under `frontend/public/`, skip files that already
  exist, sleep between calls. ~26 images ≈ $0.26 at $0.01/image. Not run by check.ps1. Emre runs it
  once with `py scripts/generate_images.py`. Mention Muse Image in the README model table.
- [ ] 27. Use `docs/philosophy-notes.md` to sharpen `prompts/aristotle.md`, `prompts/socrates.md` and
  `prompts/hypatia.md` (methods, "will not" lists, paraphrase-don't-quote rule). Keep existing tests
  green; add one test per prompt that the "will not" rules are present.

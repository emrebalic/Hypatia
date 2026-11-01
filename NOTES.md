# Notes (agents append one line per task)

## Verified API facts (read from dev.meta.ai/docs on Nov 1)
- Chat models: `muse-spark-1.3` (use this for the app), `muse-spark-1.2`, `muse-spark-1.1`, `muse-wonder-1.0`.
  Contributor variants (`muse-spark-1.3-contributor`, 1.2) are far cheaper but prompts/files may train Meta models.
- Structured output (Chat Completions): `response_format={"type": "json_schema", "json_schema": {"name": ..., "schema": {...}}}`.
  `strict` defaults to false. No recursive `$ref`; max nesting depth 10. Pydantic also works via
  `client.beta.chat.completions.parse()`.
- Transcription: `POST {META_BASE_URL}/asr/transcribe`, `Authorization: Bearer <key>`, multipart with two parts:
  - `request` (application/json): `{"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV", "mode": "DIARIZATION"}`
  - `audio` (audio/wav): mono 16-bit PCM WAV at 16 or 24 kHz, max 10 minutes, body max 32 MB.
- Transcription response: `{sessionId, transcript, audioDurationMs, turns: [{turnId, startMs, endMs, transcript, speaker}]}`.
  Times are integer milliseconds (the contract uses seconds: divide by 1000). `speaker` is a label like `A`, valid
  only within one request. No word-level timestamps. 400 = bad WAV or too long, 413 = too big, 429 = back off.
- Convert other formats: `ffmpeg -i input.m4a -ac 1 -ar 24000 -c:a pcm_s16le -map_metadata -1 output.wav`.
- Image generation (Muse Image, read from dev.meta.ai/docs/image-generation + pricing-rate-limits on Nov 1):
  `POST {META_BASE_URL}/images/generations`, OpenAI-compatible (`client.images.generate(model, prompt, n)`
  with `base_url` works). Model `muse-image-1.0` (env `META_IMAGE_MODEL`). Body: `model`, `prompt`,
  `n` 1-10 (default 1); `size` "WxH" sets the aspect ratio only, not exact pixels ("1024x1024" for
  square); `response_format` "b64_json" (default, bytes in `data[].b64_json`) or "url" (temporary signed
  URL in `data[].url`); `output_format` webp (default) / png / jpeg. Flat $0.01 per generated image
  (only successfully returned images billed, failures and safety-filtered images are free). Rate limit
  150 requests/min, no token limit. Built-in web/image search is on by default and included in the price.
- Prices per 1M tokens: Spark $1.25 in / $0.15 cached / $4.25 out; contributor $0.10 / $0.002 / $0.20.
  Voice Transcribe $0.18 per audio hour.

## Muse Code on this machine (tested Nov 1, Muse Code 1.4.14)
Shell commands inside the Windows sandbox do not work here: `py` finds no Python, `npm` fails with EPERM, `git`
reports dubious ownership, and sandbox ACL updates took minutes or timed out. Docs also say `.git` is read-only in
the sandbox. So the loop runs the agent with `--disable-shell`, and check.ps1 + git run on the host.
The loop builds with `muse-spark-1.3` at high effort ($1.25 in / $0.15 cached / $4.25 out per 1M tokens) and stops at about
$120 of estimated spend, computed from `run_usage` events in `logs/`. The estimate may miss child runs.

## Log
- task 1: backend skeleton (FastAPI /health in app/main.py, requirements.txt, .env.example, tests/test_health.py).
- task 3: backend/app/schemas.py contract models (Speaker/Segment/Node/Edge/Fallacy/DebateResult) + backend/tests/test_schemas.py validating fixtures/sample_debate.json.
- task 4: backend/app/meta_client.py (chat_json/chat_json_validated via OpenAI SDK with json_schema structured output + one retry, transcribe_wav via httpx multipart, env vars read lazily) + backend/tests/test_meta_client.py (14 offline tests, SDK + httpx faked).
- task 5: frontend skeleton (Vite 5 + React 18 + TS, @xyflow/react dep for task 13, three-column player/map/philosopher layout in src/App.tsx, non-political demo note); build not run here, left to check.ps1.
- task 6: backend/app/transcribe.py (POST /api/transcribe with ffmpeg conversion + 10-min limit + turns-to-segments/speakers mapping, POST /api/transcript paste parser) + backend/tests/test_transcribe.py (14 offline tests); code not run here, left to check.ps1.
- task 7: backend/app/analyst.py (transcript segments -> nodes+edges via meta_client structured output, prompt in backend/app/prompts/analyst.md, verified=True stamped for the task-8 verifier) + fixtures/analyst_reply.json (canned reply) + backend/tests/test_analyst.py (5 offline tests, model faked); code not run here, left to check.ps1.
- task 8: backend/app/verifier.py (deterministic quote-in-transcript + start-in-segment checks, failing items get verified=false, inputs not mutated) + backend/tests/test_verifier.py (8 offline tests incl. deliberately broken quotes/timestamps/segment ids); fixed analyst format_transcript to render speaker id + label so S1/S2 reach the model (previous check.ps1 failure).

- task 9: backend/app/fallacy.py (FallacyHunter: transcript+nodes -> fallacy drafts via meta_client structured output, then through verify_fallacies; prompt at backend/app/prompts/fallacy.md following the analyst convention for the task's `prompts/fallacy.md` path) + fixtures/fallacy_reply.json (canned reply) + backend/tests/test_fallacy.py (8 offline tests, model faked, incl. invented-quote/bad-timestamp downgraded to verified=false); code not run here, left to check.ps1.
- task 10: backend/app/semantic_verifier.py (model asks "does this quote support this label?" for deterministically-verified nodes/fallacies via meta_client structured output, downgrades supported=false to verified=false, never upgrades, skips model call when nothing eligible; prompt at backend/app/prompts/semantic_verifier.md) + fixtures/semantic_verifier_reply.json + backend/tests/test_semantic_verifier.py (11 offline tests, model faked); code not run here, left to check.ps1.
- task 11: backend/app/analyze.py (POST /api/analyze runs Analyst -> deterministic verifier -> FallacyHunter -> semantic verifier, returns DebateResult, saves backend/data/last_result.json) + backend/tests/test_analyze.py (6 offline tests, model faked); code not run here, left to check.ps1.
- task 12: frontend intake screen (src/App.tsx file upload -> /api/transcribe then /api/analyze, paste -> /api/transcript then /api/analyze, 4-stage Transcript/Arguments/Fallacies/Verify indicator + status line + error alert, audio preview, result summary) + dev /api proxy in vite.config.ts; build not run here, left to check.ps1.
- task 13: frontend/src/ArgumentMap.tsx (@xyflow/react canvas, node colour per type, supports=green / attacks=red edges, dagre top-to-bottom auto-layout + legend, speaker + timestamp on each node) wired into src/App.tsx middle column via /api/analyze result; added dagre + @types/dagre to frontend/package.json, map styles in src/App.css; build not run here, left to check.ps1.

- task 14: click node seeks player (audioRef + onNodeSelect, speaker label + MM:SS on each node, seek notice + selected highlight); replaced dagre auto-layout with a dependency-free layered layout and dropped dagre/@types/dagre from frontend/package.json so `npm ci` matches package-lock.json again (lock cannot be regenerated with file-tools-only; dagre can be restored once `npm install` runs on the host); no frontend test harness exists so verification is tsc + vite build via check.ps1; code not run here, left to check.ps1.

- task 15: frontend fallacy badges on map nodes + FallacyPanel detail card (quote, explanation, ✅/⚠️ status, play-from-quote seek) in middle column; unverified nodes/fallacies greyed with ⚠️; DebateMapNode extended with quote+verified, new DebateFallacy type; code not run here, left to check.ps1.
- task 16: backend/app/philosopher.py (POST /api/philosopher with summary+points, every point must cite real node ids or the reply is rejected; prompts at backend/app/prompts/aristotle.md, socrates.md, hypatia.md as minimal placeholders per task 24) + fixtures/philosopher_reply.json + backend/tests/test_philosopher.py (14 offline tests, model faked); code not run here, left to check.ps1.
- task 17: fleshed out prompts/aristotle.md (syllogism reconstruction + Sophistical Refutations fallacies + verdict naming who argued better) and prompts/socrates.md (no verdict, 2-3 probing questions per speaker on the weakest premise) + fixtures/aristotle_reply.json + fixtures/socrates_reply.json + backend/tests/test_aristotle_socrates.py (7 offline tests, model faked); code not run here, left to check.ps1.
- task 24: rewrote backend/app/prompts/hypatia.md as geometric proof check (per-side definitions+assumptions, ordered steps each marked holds/breaks with reason+node ids, no overall winner, Established close, writings-did-not-survive note, never any quote attributed to her) + fixtures/hypatia_reply.json + backend/tests/test_hypatia.py (4 offline tests, model faked); joined 'Sophistical Refutations' onto one line in backend/app/prompts/aristotle.md to fix the failing prompt test (task text's prompts/hypatia.md path lives at backend/app/prompts/hypatia.md per the task-16 convention); code not run here, left to check.ps1.

- task 18: frontend/src/PhilosopherPanel.tsx (choose Aristotle/Socrates/Hypatia, POST /api/philosopher, node-id chips highlight the map node, one follow-up, Hypatia writings-did-not-survive note) wired into src/App.tsx right column + styles in src/App.css; code not run here, left to check.ps1.

- task 19: demo mode (GET /api/demo in backend/app/demo.py serving backend/data/last_result.json with no model calls + "Load demo instantly" button in frontend/src/App.tsx, seeded backend/data/last_result.json from fixtures/sample_debate.json, 6 offline tests in backend/tests/test_demo.py); code not run here, left to check.ps1.

- task 20: README.md (pitch, screenshots placeholder, mermaid architecture, Meta-model table, Windows setup, "Built during the hackathon"); fixed demo.py default-arg bug (load_demo_result bound LAST_RESULT_PATH at def time, so monkeypatched path was ignored -> 404/500 tests got 200; now resolves the global at call time); code not run here, left to check.ps1.

- task 21: backend/tests/live/test_smoke.py (skipped unless RUN_LIVE=1, loads backend/.env: pasted 5-turn cafeteria-trays transcript -> /api/analyze -> /api/philosopher Aristotle, loose contract assertions, LAST_RESULT_PATH redirected to tmp_path); code not run here, Emre runs it.
- task 25: backend/app/content_api.py (GET /api/content serving content/*.json, no model calls) + frontend/src/LearnPanel.tsx (JSON-driven Learn guides replacing the static ReferencePanels, badge click opens the matching card on taxonomy_name == name) + backend/tests/test_content.py (6 offline tests incl. taxonomy exact-match + fallback SVGs on disk); fixed 8 taxonomy_name values in fallacies.json to the exact Hunter output names.
- task 26: scripts/generate_images.py (one-off Muse Image generator, stdlib only, skips existing, sleeps between calls, --limit/--force/--dry-run) + verified image API facts above + META_IMAGE_MODEL in backend/.env.example + README model-table row. Script not run here (needs key, spends ~$0.26); Emre runs `py scripts/generate_images.py` once. NOTE: AGENTS.md says the loop reverts scripts/ edits, but docs/LEARN_TASKS.md task 26 explicitly requires this file — created per Emre's direct request; re-apply if the loop reverts it.
- task 27: sharpened prompts/aristotle.md (golden-mean step), prompts/socrates.md (elenchus moves), prompts/hypatia.md (charity/steelman step); each gained a Will-not list + paraphrase-don't-quote rule; added one will-not test per prompt.
- review fixes (per Emre): CORS in app/main.py; analyze runs FallacyHunter + node semantic in parallel and degrades gracefully on hunter/semantic failure; semantic verifier fails closed (missing verdict downgrades); all 6 Learn philosophers are now judges (new prompts/kant.md, marcus-aurelius.md, epicurus.md + fixtures + tests, judge flags true) — SPEC.md MVP lists 3 judges, expanded to 6 on Emre's direct request; ArgumentMap barycenter ordering; App.tsx resultVersion key + clearAnalysisState; illustrations converted PNG->WebP 87MB->1.7MB and generator now emits WebP. Sandbox cannot run TestClient/vite (socket/ACL), so endpoint tests await host check.ps1; offline non-TestClient tests 91 passed, tsc clean.
- redesign (per Emre): aubergine-centred palette expanded (gold/burgundy/sage accents in index.css), wisdom typography (Cormorant Garamond display + Source Serif body + Inter UI via index.html), spacious shell (App.css padding/gaps/line-height up, scroll cap removed), Library is now one tabbed panel (Philosophers/Fallacies) in LearnPanel.tsx with no emoji in card text and no per-card pastel backgrounds, map/fallacy glyphs replaced with text labels and lilac-aligned node colours; all 26 card images regenerated as engraving duotone motifs (aubergine ink + gold, one classical object per card, no portraits) and placed as WebP (4.4MB total), image_prompt/style in both content JSONs rewritten to match. tsc clean, offline tests 91 passed; visual check + vite build await host (sandbox ACL).
- claude-ui review (per Emre): reviewed the other agent's uncommitted UI pass (Hamlet quote header, burgundy notice strip, dashed drag-drop upload + aligned paste column, animated PipelineFlow.tsx). Kept it; reverted its scripts/check.ps1 edit (protected file, loop restores it; gate semantics back to npm ci), made the flow travelling-light active-link-only (idle links no longer look busy), fixed dropzone dragleave flicker on children, moved the Library below the intake section. tsc clean, offline tests 91 passed; drag-drop and live animation not exercised here (sandbox), left for host visual check.

## Blocked

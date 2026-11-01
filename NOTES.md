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

## Blocked

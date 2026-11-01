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

## Blocked

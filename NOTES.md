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

## Blocked

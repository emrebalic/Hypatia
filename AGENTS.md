# Rules for coding agents working on Hypatia

Read `SPEC.md` first, then `TASKS.md` and `NOTES.md`. SPEC.md is the source of truth; if a task conflicts with it, follow SPEC.md and note the conflict in `NOTES.md`.

## Working loop
`scripts/run-loop.ps1` drives you. It runs you with **file tools only: no shell, no web**.
1. Do only the task named in your prompt, with the smallest change that satisfies it.
2. You cannot run anything. Write code carefully, and write the tests with it. After you stop, the
   script runs `scripts/check.ps1` (pytest + frontend build) and, on failure, starts you again with
   the error output. Your changes stay in the working tree between attempts.
3. Tick the box in `TASKS.md` and append one line to `NOTES.md` (what changed, anything uncertain).
4. Do not run git. The script commits only when check.ps1 passes and the box is ticked.
5. If the task cannot be finished (missing fact, needs a decision), write why in `NOTES.md` under
   `## Blocked`, leave it unticked, and stop.

## Because you cannot run commands
- No scaffolding tools: write files such as `frontend/package.json` and `vite.config.ts` by hand.
- `pip install` and `npm install` run inside check.ps1. Add only well-known packages, never one you
  are unsure exists. Do not hand-write `package-lock.json`; it is generated and committed for you.
- Backend tests live in `backend/tests/` and run with `backend/` as the working directory.

## Environment
- Windows + PowerShell. Scripts are `scripts/*.ps1`, never bash-only syntax. Python 3.12 (`py -3.12`).
- Secrets live only in `backend/.env` (gitignored). Never write a key anywhere else. The repo is PUBLIC.

## Meta Model API
Verified facts (endpoints, model IDs, limits) are in `NOTES.md` under `## Verified API facts`. Use
them; do not guess API shapes.
- Chat: `OpenAI(base_url=os.environ["META_BASE_URL"], api_key=os.environ["META_API_KEY"])`.
- Transcription is NOT an OpenAI SDK call: use `httpx` as described in NOTES.md.
- Model IDs come from env vars only (`META_TEXT_MODEL`, `META_TRANSCRIBE_MODEL`).
- Prefer structured output; always validate with pydantic and retry once on invalid JSON.
- All network calls go through ONE module: `backend/app/meta_client.py`, so tests can mock it.

## Testing
- Unit tests must run offline: mock `meta_client`. Use `fixtures/` for inputs and canned model replies.
- Add a test for every bug you fix.
- Live API calls only in `backend/tests/live/` and only when `RUN_LIVE=1`. check.ps1 does NOT run them.

## Don'ts
- Do not download media from YouTube or other sites.
- Do not add auth, databases, Docker, or deployment unless a task says so.
- Do not rewrite working modules for style. Do not delete tests to make check.ps1 pass.
- Do not change SPEC.md, AGENTS.md, CLAUDE.md, `.gitignore` or `scripts/`: the loop reverts such edits.

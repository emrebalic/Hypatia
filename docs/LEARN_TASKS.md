# Learn panel — tasks to append to TASKS.md

Content is ready (added by Emre, Nov 1):
- `docs/philosophy-notes.md` — knowledge base on how each philosopher thinks. Read it before touching
  philosopher prompts.
- `backend/app/content/philosophers.json` and `fallacies.json` — short card texts, colours, emoji,
  Muse Image prompts, `image` (PNG, to be generated) and `fallback_image` (SVG, already present).
- `frontend/public/illustrations/*.svg` — warm fallback badges, one per card.

Priority: do these **after** the core demo works. If time is short, task 25 alone is enough
(the SVG fallbacks already look fine). Cut 27 first.

## Phase 6 — Learn & delight
- [ ] 25. Learn panel UI: a "Learn" tab/drawer listing philosopher cards (from `philosophers.json`) and
  fallacy cards (from `fallacies.json`). Each card: image (`image`, falling back to `fallback_image` on
  load error), name, one-line tagline, expandable summary/method/example/tip. Clicking a fallacy badge
  on the map opens its card (match on `taxonomy_name` == fallacy `name`). Warm, soft styling using each
  card's `colors`. Serve the JSON via `GET /api/content` (static, no model call). Add tests.
- [ ] 26. `scripts/generate_images.py`: one-off generator using **Muse Image** through Meta Model API.
  First read https://dev.meta.ai/docs (Muse Image page) and record the exact endpoint, model id and
  parameters in NOTES.md — do not guess. Read every `image_prompt` from both JSON files, request a
  square image, save to the card's `image` path under `frontend/public/`, skip files that already
  exist, sleep between calls. ~26 images ≈ $0.26 at $0.01/image. Not run by check.ps1. Emre runs it
  once with `py scripts/generate_images.py`. Mention Muse Image in the README model table.
- [ ] 27. Use `docs/philosophy-notes.md` to sharpen `prompts/aristotle.md`, `prompts/socrates.md` and
  `prompts/hypatia.md` (methods, "will not" lists, paraphrase-don't-quote rule). Keep existing tests
  green; add one test per prompt that the "will not" rules are present.

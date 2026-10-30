---
name: mvp-demo
description: Record and edit a short demo video of a running web app with Playwright and ffmpeg. Use for a hackathon demo, screencast, walkthrough or "record my app". Default to no voice; add narration or TTS only when the user requests it.
---

# MVP demo video

Make a short, honest video of a product that really runs. Drive the browser with code and make the evidence readable.
The team's current choice is **no voice and no TTS**. Use callouts and timed holds; do not synthesize speech, install
speech engines, request voice credentials or block recording on narration approval. The user will ask if voice is needed later.

## What you deliver
- `demo.mp4`: H.264 + AAC (silent audio track by default), 1280x720 or 1920x1080, under the length limit.
- Storyboard with scene timings, actions, evidence and short on-screen callouts. Narration is optional.
- A video description with honest notes about anything shortened or staged and sources for numbers actually shown.
- Draft cuts along the way: send a first rough cut early; the user will spot things you cannot (a stall, a hidden panel, a word that sounds wrong).

## The kit (scripts/)
- `demo_kit.py`: `tts()` voice clips with word timings and subtitle phrases; `record_segment()` records one browser segment with the overlay; `Segment` helpers (`beat`, `on_words`, `click`, `type`, `chip`, `camera`, `fast_forward`, `hold`, `trim_start`, `end_here`); `assemble()` cuts, fades, places every voice clip, adds optional ducked music, normalises loudness; `check_overlaps()`; `contact_sheet()`; `make_slide()`; `make_spotlight()`. CLI: `python demo_kit.py assemble|check|sheet|voices`.
- `overlay.js`: injected into every page: chip, cursor, subtitles that dodge content, camera zoom, and a ticking pixel that keeps frames coming.
- `example_demo.py`: an offline machine check, silent by default; it writes outside the contest repo. Its toy app and example figures are not product evidence. Use the recording pattern, not its illustrative claims, for the real demo.
- `assets/slide.html`, `assets/spotlight.html`: templates used by `make_slide` and `make_spotlight`.

Setup in a personal venv: `python -m pip install -r <skill-folder>/requirements.txt`, then
`python -m playwright install --no-remove chromium`. If Chrome is already installed, only
`python -m playwright install --no-remove ffmpeg` is needed; the kit can launch Chrome instead of downloaded Chromium.
Use `--no-remove` (or `PLAYWRIGHT_SKIP_BROWSER_GC=1`) to preserve browsers cached by other tools. The pinned dependencies
are Playwright and imageio-ffmpeg (which supplies the encoder used for assembly).
Recommended Windows venv Python: `$HOME/.agents/tools/mvp-demo/.venv/Scripts/python.exe` (quote paths with spaces).
Run `python scripts/example_demo.py --out <personal-output-folder>` with that interpreter. No speech package or API key is needed.

## Workflow

### 1. Gather the facts first
Ask for, or find in the repo: the rules of the video (length, language, where it is uploaded, what must be shown: for a hackathon read the rules page or the repo's digest of it), the app (URL, how to start it, test logins, how to reset or seed its data), the story (problem, who it is for, what is new), the sponsor technology that must be visible, and what may not be shown (secrets, e-mail addresses, account ids, third-party logos, copyrighted music). Check that the app actually runs before writing a word.

### 2. Storyboard (read references/storyboard.md)
Plan the strongest working flows, actions, short callouts and holds within the time limit. Follow the project's video
brief before generic pitch advice. For Product Truth Passport, start with `references/passport-storyboard.md`: running
app and system flow only, no pitch slides or market numbers. Do not require a narration script for a silent demo.

### 3. Choose the audio mode
Default: pass an empty clips dictionary to `record_segment`, omit `beat`/`on_words`/`finish`, and use `chip`, `hold` and
`at` for visual timing. No dummy speech clips are needed. Keep any contract-reserved `narration.json` as `{}`.
Only if the user requests narration, read `references/voice.md`, choose an engine and review its text before recording.
`tts()` defaults to the offline `silent` engine as a safeguard; real speech requires an explicit engine and optional dependencies.

### 4. Record segments (read references/recording.md)
One segment per scene, each in its own function, so a single scene can be re-recorded without touching the others. Inside a segment:
- In silent mode, use short `seg.chip(...)` callouts and explicit holds. Only in narrated mode, use `beat` and `on_words`.
- Use the real app with real data. Seed it so the story is reproducible; reset state between takes (bookings, counters, idempotency keys, logins).
- Waits nobody needs to watch (loading, an AI thinking, typing) are recorded in full and fast-forwarded with `seg.fast_forward(start)`; never fast-forward while a voice is speaking.
- After every result, `seg.hold(1.5-2.5)`: the screen stays still at normal speed so a viewer can read it or pause.
- Make evidence visible: enlarge traces and decision panels with `seg.camera` or recording-only CSS. App changes stay in the owning lane; send a CCR when necessary.
- Callouts (`seg.chip`) say what the viewer should notice, in a few words.

### 5. Assemble and check (read references/editing.md for transitions, music and other recipes)
`assemble(names, seg_dir, Path("demo.mp4"))`, then `check_overlaps(names, seg_dir)` (no two voices at once, no fast-forward under a voice), then `contact_sheet()` at the key moments and look at the frames yourself: subtitles over content, a stale chip, a half-finished zoom, an answer that is cut off or duplicated, a frame where nothing happens. Read references/qa.md before sending a cut.

### 6. Iterate and deliver
Send the cut with a short honest list: what changed, what is still weak, what is staged (shortened timers, scripted extra users, edited answers). When the user points at a moment ("at 1:56 the voices overlap", "the tool calls are missing"), find the cause in the recording or the app rather than masking it. Re-record only the segment that changed. Deliver the final MP4, the description text, and a note of where the scripts live so the video can be rebuilt.

## Principles that make the video work
- **Real, not mocked.** Judges notice fakes. Record the running app; when something is staged (a timer set to minutes instead of hours, a crowd of scripted users), label it on screen and in the description.
- **Every second earns its place.** No dead air: cut page loads (`trim_start`), fast-forward waits, end a segment as soon as its point is made (`end_here`). Then spend the saved seconds on holds where the viewer must read.
- **One idea per scene.** A short callout names the point and the screen proves it. Voice is optional.
- **Readable at 720p on a phone.** Large text, zoom on small panels, subtitles that never cover the thing being shown.
- **Honest numbers.** Every number on a slide has a source and date on the slide; measured numbers say how they were measured.
- **AI outputs vary.** When the app uses a model, its answers differ per take and may invent facts. Check each take for made-up numbers or claims (a small regex check works), retake, and fix the app's prompt or messages when the cause is there. Never edit an AI answer to say something it did not say; cutting or fast-forwarding it is fine and should be disclosed.

## Running this skill in Codex (port notes, 2026-10-29)
- Invoke with `$mvp-demo` (or pick it from `/skills`). Codex reads this folder from `~/.agents/skills/mvp-demo/` or a repo's `.agents/skills/`; the `.skill` zip is a claude.ai upload format, so the skill ships here as a folder. `agents/openai.yaml` holds the Codex UI metadata.
- The kit lives next to this file (`scripts/demo_kit.py`, `scripts/overlay.js`, `assets/`). This repo deliberately tracks the prepared bundle under `_outside-repo/skills/mvp-demo`; keep it separate from backend/frontend application code. Import it from that folder or a user-installed skill (`DEMO_KIT_DIR` points to its scripts/) and write the contest-specific recorder in `scripts/demo/record_demo.py` on the day.
- Installation and the Chromium download need network access. After setup, recording local pages and assembling silent video work offline. Respect the current execution permissions; do not change sandbox settings implicitly.
- Windows: quote paths with spaces; set `PYTHONIOENCODING=utf-8`; ffmpeg comes from imageio-ffmpeg. Only when voice is requested, list optional Vietnamese voices with `python scripts/demo_kit.py voices --lang vi-`.
- The kit is a pre-existing personal video tool included as prepared setup in this repo's init commit. Declare its source, purpose and preparation date separately from application implementation. Do not claim it was written during the event. Declare a synthetic voice only if one was actually used.
- Product Truth Passport: start from `references/passport-storyboard.md`.

## When the user asks for something else
- A quick screen capture without narration: record with `clips={}` and assemble; no TTS clip is needed.
- Voice in another language: pick an edge-tts voice (`python demo_kit.py voices --lang vi-`), or the user's own recorded voice as WAV files with word times from a forced aligner (see references/voice.md).
- A pitch with no app yet: slides plus a spotlight on mockups, clearly called a concept.

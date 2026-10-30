# Checking a cut before sending it

## Automatic
- `check_overlaps(names, seg_dir)`: no overlapping voices, no fast-forward under a voice, and no voice cut off by its scene ending. Silent segments must pass with no clips. Zero problems before sending.
- Length under the limit with a reserve (`demo_kit.duration("demo.mp4")`).
- Only for narrated videos: `ffmpeg -i demo.mp4 -af silencedetect=noise=-45dB:d=2 -f null -` lists audio gaps of 2 s or more. Silence is intentional throughout the default no-voice video.

## Look at frames (contact_sheet at the start, middle and end of every scene, and at each hold)
- The point of the scene is visible and readable at 720p: results, the trace or log that proves it, the numbers.
- Subtitles never cover the thing being shown; the chip is not stale (it matches the scene).
- No half-finished zoom or transition on a hold frame.
- Nothing appears twice (a repeated AI answer whose text arrived before its audio: cut at the first sign of the repeat, text or audio).
- No secrets or personal data: e-mail, account ids, tokens, real names.
- Staged parts are labelled on screen.

## Listen (only if voice was requested)
- Every voice clip starts at the moment its action happens; no clipped first word (cut points 0.1 s before a word).
- Volume steady between narration and recorded audio (loudnorm handles most; a recorded app voice may need `volume=1.5`).

## Common faults and their causes
| Symptom | Cause | Fix |
|---|---|---|
| The video stalls with nothing happening | a static page with no frames, or a long wait | the overlay tick keeps frames; fast-forward the wait; `end_here` sooner |
| Voice and picture drift apart in a scene | a fast-forward that runs under the voice | `finish()` the beat before starting the wait |
| Subtitles appear over content | the page grew under them | mark the area `data-ink`, keep the bottom 118 px free |
| Only part of a list is visible | the app's panel has its own `max-height` and scrollbar | fix the app's CSS (it hides it from users too), or zoom out |
| Click does nothing in the take | an overlay or a running zoom transition covered the element | wait for the camera to settle, check `pointer-events` |
| The AI says something false | the model guessed (often after an error without a reason) | retake with a fact check; fix the prompt or the error message |
| A take fails on the second run | state left by the first take (bookings, tickets, keys, a held slot, a used-up counter) | a reset function run before every take |
| `window.something is not a function` | the init script threw before defining it (it ran before `document.documentElement` existed) | guard every DOM access inside the injected script |

## Before delivering
- Watch the whole video once at normal speed, as a judge would.
- Write the description (honest notes, sources) and the as-made storyboard.
- Keep the scripts and the voice cache: the next fix is a re-render, not a redo.

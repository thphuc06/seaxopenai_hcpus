# Recording with Playwright

## Contents
1. A segment, step by step
2. Signing in and seeding data
3. Making the page camera-ready (CSS injection)
4. Timing actions to the voice
5. Waits, holds and cuts
6. Diagrams with a spotlight
7. Apps with AI answers (nondeterminism, retakes)
8. Voice apps: a fake microphone and the assistant's audio
9. How the recorder behaves (why the kit does what it does)

## 1. A segment, step by step
The current default is **no narration**. Record directly with no clips:
```python
import demo_kit as K

def checkout(seg):
    seg.page.goto(f"{BASE}/cart")
    seg.trim_start()
    seg.chip("Two items in the cart")
    seg.hold(1.5)
    seg.click("#pay")
    waited = seg.now()
    seg.page.wait_for_selector(".receipt")
    seg.fast_forward(waited, to=0.8)
    seg.chip("Receipt created")
    seg.camera(".receipt", 1.5)
    seg.hold(2.0)
    seg.end_here()

K.record_segment("checkout", {}, checkout, SEG, setup=sign_in)
```

The following word-timed variant is optional, only after a request for narration and an explicit engine choice:
```python
import demo_kit as K
clips = {k: K.tts(v, engine="edge") for k, v in NARRATION.items()}

def checkout(seg):
    seg.page.goto(f"{BASE}/cart")
    seg.trim_start()                      # cut the page load
    seg.beat("cart")                      # the voice starts here, subtitles too
    seg.chip("Two items in the cart")
    seg.on_words([("pay", lambda: seg.click("#pay"))])
    seg.finish(tail=0.2)                  # wait for the voice to end
    t = seg.now()
    seg.page.wait_for_selector(".receipt")
    seg.fast_forward(t, to=0.8)           # the payment wait plays in 0.8 s
    seg.beat("receipt"); seg.camera(".receipt", 1.5); seg.finish(tail=0.2)
    seg.hold(2.0); seg.end_here()

K.record_segment("checkout", clips, checkout, SEG, setup=sign_in)
```
One segment = one recording file = one function. Re-record one scene without touching the others; assemble them in any order.

## 2. Signing in and seeding data
- Sign in off camera through the browser context: `setup=lambda ctx: ctx.request.post(f"{BASE}/login", form={...}, max_redirects=0)` (cookies land in the context). Or `ctx.add_cookies([...])`, or a saved `storage_state`.
- Seed the data the story needs with the app's own seed script or API, from Python, before the segment. Keep a reset function: re-takes must start from the same state (bookings removed, counters reset, idempotency records cleared, extra users created and deleted).
- A crowd (other users, other entries): create them through the real API with scripted users and say so in the video.

## 3. Making the page camera-ready
Inject CSS from the segment (`seg.ev("() => { const s = document.createElement('style'); s.textContent = '...'; document.head.appendChild(s); }")`):
- If subtitles are enabled, keep the bottom ~118 px free. A silent video with callouts only need not reserve subtitle space.
- Hide what distracts (intro text, cookie banners), enlarge small text (`main{zoom:1.15}`), or zoom out a long list (`main{zoom:.8}`) so the answer and its evidence fit one frame.
- A page's own stylesheet may load after yours: use `!important` when an override does not take (check with `getComputedStyle`).
- Auto-scroll for chat-like pages: a `MutationObserver` that scrolls to the bottom on every change, injected with `page.add_init_script` (pass `init_scripts=` to `record_segment`).
- Test the layout with `page.screenshot()` on injected sample content before a long take.

## 4. Timing actions to the voice
- `seg.on_words([(word, action)])`: the action runs 0.25 s before the word is spoken; each word once. Actions are JS strings run in the page or Python callables.
- `seg.at(seconds)`: wait until N seconds into the current beat. `seg.finish(floor, tail)`: until the voice ends.
- Typing: `seg.type(selector, text, delay_ms=45)` reads naturally; for long text (a pasted code) use `page.fill` so the result lands while the voice names it.
- Clicks go through the real mouse (`seg.click`), so the cursor moves visibly and the app reacts as it would for a person. If an overlay or animation blocks a click, wait for it to settle (`seg.camera` already waits 1.1 s) or click by JS as a last resort.

## 5. Waits, holds and cuts
- Fast-forward waits after the voice has finished (`seg.finish()`, then `t = seg.now()`, wait for the result, `seg.fast_forward(t, to=0.8)`). `check_overlaps` flags any fast-forward that runs under a voice.
- Hold after each result (`seg.hold(1.5-2.5)`). People pause videos on results; give them a still frame.
- `seg.trim_start()` drops a slow first load; `seg.end_here()` ends the segment right after its point.
- For a long recorded answer (an AI that talks for 20 s), keep the first seconds of its audio, fade it out, fast-forward the rest of the video until the full text is on screen, then hold (see references/editing.md, "Shortening a recorded answer").

## 6. Diagrams with a spotlight
`make_spotlight(page, image, {"gw": ((x, y, w, h), "Front door"), ...})` builds a page with `focus(name)` and `focus('all')`. Coordinates are in the image's own pixels: open the PNG in any viewer, or read them from the source (draw.io: the `mxGeometry` of each cell, scaled to the export size). Fire `focus` from `on_words` as each part is named, end on `focus('all')` and hold 1.5 s so the zoom-out completes. Wait for `window.spotlightReady === true` before the beat.

## 7. Apps with AI answers
- Answers differ per take. Write a small check that reads the transcript (from the page or from the app's log) and flags invented facts: numbers, limits, phone numbers, prices that no tool or data gave. Retake until clean, and cap the retakes.
- If the model keeps inventing the same thing, the cause is upstream (a prompt, an error message without a reason). Fix the app, rerun its tests, then retake; tell the user what was fixed.
- A model may repeat tool calls or speak its reasoning. Show the duplicates if they are in the trace (honest), cut a repeated spoken answer, and retake a take where the model talks to itself.
- Long waits for the model are fast-forwarded; keep a visible "working" state on screen so the viewer knows why.

## 8. Voice apps: a fake microphone and the assistant's audio
For an app that listens to a microphone (`getUserMedia`) and speaks through Web Audio:
```js
// init script: the page's microphone is an AudioContext stream we feed with PCM from Python
let ctx = null, dest = null;
const fake = async () => { if (!ctx) { ctx = new AudioContext({sampleRate: 16000}); dest = ctx.createMediaStreamDestination(); } await ctx.resume(); return ctx; };
navigator.mediaDevices.getUserMedia = async () => { await fake(); return dest.stream; };
window.__speak = async (b64) => { const c = await fake(); /* decode 16-bit PCM to a buffer, play it into dest */ };
```
Generate the user's lines with a TTS at the app's input rate, call `window.__speak` from Python, and wait for the app to answer before the next line (watch its WebSocket messages or DOM, not a timer). Capture the assistant's audio by wrapping `window.WebSocket` and storing the audio messages with timestamps, then write them as WAV clips and add them as marks (`seg.marks.append((ms, wav))`). Headless Chrome plays no sound into the recording, so every audio you want in the video must become a clip.

## 9. How the recorder behaves
- Playwright writes video frames only when the page repaints; a still slide leaves no frames and the clock drifts. The overlay's ticking pixel prevents this, and `record_segment` measures where the video really starts from its length.
- The video size is fixed per context (`viewport=(1280, 720)` by default); use 1920x1080 for crisper text, at the cost of bigger files and slower runs.
- Run headless; a visible browser on a remote desktop is slow and steals focus.
- Close contexts and browsers created by the recorder. If a take crashes, clean up only the recorder's identified process; never kill every Chrome process on the user's machine.

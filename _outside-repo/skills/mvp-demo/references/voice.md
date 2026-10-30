# Voice: engines, timings, subtitles

Optional reference: read this only when the user requests voice. The current team demo is silent, so do not install
edge-tts/boto3 or generate speech by default. `tts()` now defaults to `engine="silent"`; call an explicit speech engine
only after the user asks. A silent recording normally uses `clips={}` and does not call `tts()` at all.

The kit needs, for each beat, a WAV file and the time (ms) at which each word starts. Word times drive the subtitles and the actions on screen, so an engine without them still works but timing becomes approximate (the kit spreads words evenly).

## Engines
| Engine | Cost | Word times | Notes |
|---|---|---|---|
| `edge` (edge-tts, Microsoft Edge online voices) | free | yes (`WordBoundary`) | Optional, explicit `engine="edge"`. Needs an additional edge-tts install and internet. Many languages; the kit falls back when a voice is unavailable. Not an official API: keep a second engine in mind for a deadline. |
| `polly` (Amazon Polly, neural) | per character; speech marks are a second request and are billed too | yes (speech marks) | Needs AWS credentials. Good English male/female voices (Stephen, Matthew, Joanna...). |
| `silent` | free | estimated | For layout and timing work offline. |
| Others (add a branch in `tts`) | varies | varies | Azure Speech (word boundary events), Google Cloud TTS (SSML marks), OpenAI or ElevenLabs TTS (timestamps depend on the API), Piper or Coqui (offline, no times: use a forced aligner), Windows SAPI / macOS `say` (offline, basic). Check the current docs and prices before choosing; they change often. |
| The user's own voice | free | via a forced aligner | Record one WAV per beat; get word times with a forced aligner (for example WhisperX or aeneas), or skip word-timed actions. |

Adding an engine: write `_name(text, voice, rate, stem) -> words` that writes `stem.wav` (any rate, the kit converts) and returns `[{"time": ms, "value": word}]`, then register it in the dict inside `tts`.

## Several voices
Use one narrator and, for a scripted user or customer, a second voice of the other gender, so the viewer always knows who speaks. An AI assistant in the app speaks with its own voice (recorded from the app). State in the description which voices are synthetic.

## Making it sound right
- Write for the ear: numbers in words, acronyms spelled the way they are said ("S three" for S3, "M F A"), product names with the pronunciation you want ("Alexa plus"). Map them back for subtitles with `DISPLAY`.
- Rate: start at normal; a slightly slower rate (`-5%` on edge, `90%` on Polly) helps non-native listeners. Do not speed narration up to fit time: cut words instead.
- Listen to one beat before rendering all of them; a mispronounced name is cheaper to fix in the text.
- Short pauses: end a sentence with a full stop; for a longer pause split the beat in two.

## Subtitles
`phrases()` breaks at punctuation or ~46 characters, so a subtitle is at most two short lines and changes with the speech. The overlay places it at the bottom, or the top, or a little higher, wherever nothing readable sits under it, and moves it if the page changes. Mark a background element with `data-bg` if subtitles may cover it, or an element with `data-ink` if they must never cover it. For a platform that wants a separate caption file, write an SRT from the clip chunks and the timeline (see references/editing.md).

## Cost control
Clips are cached by (engine, voice, rate, text), so only changed lines are synthesised again. With a paid engine, print the characters sent per run and keep drafts on `silent` or `edge`.

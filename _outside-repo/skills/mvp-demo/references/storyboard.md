# Storyboard and narration

Default to a silent video: plan screen actions, short callouts and reading holds. Narration and its word budget apply
only if the user asks for voice. Product-specific briefs override this generic pitch outline; Product Truth Passport
uses `passport-storyboard.md` and does not require pitch slides, market figures or a narration approval step.

## What judges and viewers need, in order
Hackathon pages usually ask the same thing in different words ("lead with the problem, show the solution working, say who it is for, how it uses the track's technology, and what the working app actually does"). Judges may stop watching at the limit, so the best material goes first.

| Scene | Purpose | Typical length in a 3:00 video |
|---|---|---|
| Hook | the problem, with 2-4 real numbers and their sources | 8-15 s |
| Who and why | who it is for; how it differs from what exists (a 3-row comparison) | 10-15 s |
| How it works | one architecture diagram, spotlight on each part as it is named | 20-30 s |
| Demo 1 (best) | the core flow in the real app, end to end | 30-45 s |
| Demo 2..n | the second strongest flow, a refusal or edge case, the admin/owner view | 15-35 s each |
| Evidence | measured numbers (tests, evaluation, benchmarks, users) | 6-10 s |
| Close | repo or link, how to run it, one line of what is next | 4-8 s |

Rules of thumb:
- Keep a reserve of 5-10 s under the limit: platforms trim, and a re-cut always grows.
- If the brief requires sponsor technology, make it visible on screen in a callout or diagram. Name it in narration only if voice was requested.
- If a step takes long in reality (an AI answer, a deployment, a lottery that runs hours later), say so and show it shortened, labelled ("Demo: the draw was set minutes after entry").
- Drop a scene rather than rush all of them.

## Writing the narration
- About 2.3-2.6 words per second at a natural rate. A 10 s scene holds 23-26 words.
- Short sentences, one point each. Spoken words, not written ones: "three hundred and twenty trials", then map to "320" for the subtitles with `demo_kit.DISPLAY`.
- Say what the viewer should look at just before it happens; the action follows the word (the kit fires actions 0.25 s before the word).
- Numbers with sources go on the slide (small grey line under the number: publisher and date). Search the web for current figures and keep the links in the storyboard file; never invent a statistic.
- The comparison with existing solutions is a small table: approach, who decides, what goes wrong. Name categories rather than attacking a company.
- End scenes on a result, not on a loading screen.

## Storyboard file
Write `storyboard.md` next to the scripts before recording:
```
| # | Time | Scene | Callout / optional narration | On screen | Proof it shows | Source / note |
```
If voice is requested, use the same scene keys for the narration dictionary; otherwise leave it empty. Update the table
to "as made" after the final cut so it documents the actual video.

## Honesty notes for the description
List: synthetic voices (which engine), what was fast-forwarded or cut, staged data or users, shortened timers, edited (shortened) AI answers, and the date the numbers were measured. Judges reward candour; a hidden trick found later costs more than it saved.

## Trademarks, music, privacy
- No third-party logos; a source name as text under a number is a citation. If unsure, ask the user.
- No copyrighted music. Royalty-free music needs its license noted; silence under a voice is fine.
- Never show real e-mail addresses, account ids, keys, tokens or personal data. Use test accounts with obviously fake names.

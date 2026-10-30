# Editing with ffmpeg

`assemble()` covers the usual cut: per segment it trims, fast-forwards (`setpts`), converts to a constant frame rate, holds the last frame if the recording is short, scales, fades in and out (0.25 s through black), then joins the segments, places every voice clip with `adelay`, mixes with `amix`, optionally ducks music under the voice, and normalises loudness to -16 LUFS. The recipes below are for what it does not do. `FF` is `demo_kit.FF` (the ffmpeg path).

## Crossfade between two finished clips (instead of the dip to black)
```bash
# a.mp4 lasts 12.0 s; 0.5 s overlap; the audio crossfades as well
ffmpeg -i a.mp4 -i b.mp4 -filter_complex \
 "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=11.5[v];[0:a][1:a]acrossfade=d=0.5[a]" \
 -map "[v]" -map "[a]" out.mp4
```
Other transitions: `wipeleft`, `slideup`, `circleopen`, `dissolve`, `smoothleft`. Every crossfade shortens the total by its duration, and every voice after it moves earlier by the same amount: apply crossfades to finished segments that already carry their audio, or shift the marks.

## Background music
`assemble(..., music=Path("music.mp3"), music_db=-24)` loops it under the video and ducks it while the voice speaks (`sidechaincompress`). Use royalty-free music only and note its license. Many judging guidelines prefer no music at all; silence is safe.

## Shortening a recorded answer (an AI that talks too long)
Keep the first N seconds of its audio with a short fade, fast-forward the video until the full answer is on screen, then hold:
```python
# keep 4.5 s with a 0.4 s fade (16-bit mono WAV)
run(["-i", "answer.wav", "-af", "atrim=0:4.5,afade=t=out:st=4.1:d=0.4", "answer_cut.wav"])
seg.speedups.append((start + 4.6, start + full_len, (full_len - 4.6) / 0.7))   # the rest of it in 0.7 s
```
A read-back that matters (a price, a confirmation) is better kept whole and sped up slightly with `atempo=1.25` (pitch kept). Mention edited answers in the description.

## Speed up or slow down audio
`-af atempo=1.25` (0.5-2.0 per filter; chain two for more). Avoid on narration; use on recorded app audio only.

## Subtitles as a file (SRT) instead of burned-in
From `timeline()` and each clip's `chunks`: start = clip start on the timeline + chunk `t`, end = + chunk `e`. Write `index`, `HH:MM:SS,mmm --> HH:MM:SS,mmm`, text. Upload the SRT next to the video (YouTube), or burn it with `-vf subtitles=demo.srt` (needs a fontconfig-enabled ffmpeg).

## Picture-in-picture (a webcam or a phone screen)
```bash
ffmpeg -i main.mp4 -i cam.mp4 -filter_complex "[1:v]scale=320:-2[p];[0:v][p]overlay=W-w-24:H-h-24" -c:a copy pip.mp4
```

## Export settings
- YouTube/Vimeo: H.264 (`-c:v libx264 -crf 18-20 -pix_fmt yuv420p`), AAC 160 kbps 48 kHz, `-movflags +faststart`, 30 fps. 720p is enough for a UI demo; 1080p if text is small.
- Check length with `demo_kit.duration()`; keep a few seconds under the limit.
- A thumbnail: export a strong frame (`ffmpeg -ss 12 -i demo.mp4 -frames:v 1 thumb.png`) and add a title in an HTML slide if needed.

## Known ffmpeg traps
- `-shortest` with `apad` can run forever: give the final length with `-t` instead (the kit does).
- Concatenating with `-c copy` needs identical codecs, sizes and frame rates (the kit encodes every segment the same way).
- Windows builds without fontconfig need `fontfile=` for `drawtext`, with the drive colon escaped (`C\:/Windows/Fonts/arial.ttf`).
- A WebM from a browser has a variable frame rate; convert with `fps=30` before trimming by frame counts.

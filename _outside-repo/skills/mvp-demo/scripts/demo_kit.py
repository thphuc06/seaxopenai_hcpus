"""demo_kit: record a web app with Playwright, then cut it with ffmpeg. Voice is optional.

The idea: a demo video is a list of *segments*. Each segment is one browser recording driven by a small Python function,
with narration *beats* (one voice clip each) whose words can trigger actions on screen. The assembler trims each segment,
fast-forwards the boring waits, keeps a pause on every result, places each voice clip at the right moment, adds short
fades between segments and mixes everything into one MP4.

    from demo_kit import tts, record_segment, assemble, check_overlaps, contact_sheet, make_slide

Python 3.10+, the pinned ../requirements.txt (Playwright and imageio-ffmpeg), and a browser
for Playwright (`python -m playwright install chromium`, or an installed Chrome with channel="chrome").
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
OVERLAY_JS = (HERE / "overlay.js").read_text(encoding="utf-8")


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        path = shutil.which("ffmpeg")
        if not path:
            raise SystemExit("ffmpeg not found: pip install imageio-ffmpeg, or install ffmpeg")
        return path


FF = ffmpeg()


def run(args: list[str]) -> None:
    subprocess.run([FF, "-y", "-loglevel", "error", *args], check=True)


def duration(path: Path | str) -> float:
    r = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        raise RuntimeError(f"cannot read the duration of {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# =============================================================================================== voice
@dataclass
class Clip:
    """One narration beat: a mono WAV, its length, its words with times (ms) and the subtitle phrases."""
    text: str
    wav: Path
    dur: float
    words: list[dict]                      # [{"time": ms, "value": "word"}]
    chunks: list[dict] = field(default_factory=list)   # [{"t": ms, "e": ms, "text": "..."}]


DISPLAY: list[tuple[str, str]] = []        # (spoken regex, written) pairs for subtitles, e.g. (r"Alexa plus", "Alexa+")
EDGE_VOICES = ("en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-GB-RyanNeural")


def tts(text: str, *, engine: str = "silent", voice: str | None = None, rate: str | None = None,
        cache: Path = Path(".demo_cache")) -> Clip:
    """Speak `text` once and cache the result by (engine, voice, rate, text): a re-render costs nothing.

    engine="edge"   optional Microsoft Edge voices (additional edge-tts install and internet), word timings included.
    engine="polly"  Amazon Polly neural voices (boto3 credentials; billed per character, word marks billed again).
    engine="silent" default: no speech, timings estimated at 2.5 words/s. Normally record silent video with clips={}.
    Any other engine: add a branch that writes an audio file and returns word times (see references/voice.md).
    """
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(f"{engine}|{voice}|{rate}|{text}".encode()).hexdigest()[:16]
    wav, marks = cache / f"{tag}.wav", cache / f"{tag}.words.json"
    if not (wav.exists() and marks.exists()):
        words = {"edge": _edge, "polly": _polly, "silent": _silent}[engine](text, voice, rate, cache / tag)
        marks.write_text(json.dumps(words), encoding="utf-8")
    with wave.open(str(wav)) as w:
        dur = w.getnframes() / w.getframerate()
    words = json.loads(marks.read_text(encoding="utf-8"))
    shown = _align(text.split(), words) or words
    return Clip(text, wav, dur, words, phrases(shown, int(dur * 1000)))


def _to_wav(src: Path, dst: Path) -> None:
    run(["-i", str(src), "-ar", "24000", "-ac", "1", str(dst)])


def _edge(text, voice, rate, stem: Path) -> list[dict]:
    import edge_tts

    async def speak(v):
        com = edge_tts.Communicate(text, v, rate=rate or "+0%", boundary="WordBoundary")
        audio, words = bytearray(), []
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
            elif ch["type"] == "WordBoundary":
                words.append({"time": int(ch["offset"] / 10_000), "value": ch["text"]})   # offsets are in 100 ns
        return bytes(audio), words

    last = None
    for v in ([voice] if voice else []) + [x for x in EDGE_VOICES if x != voice]:
        try:
            audio, words = asyncio.run(speak(v))
            break
        except Exception as e:                       # some voices are not served in every region: try the next
            last = e
    else:
        raise RuntimeError(f"edge-tts failed for every voice: {last}")
    mp3 = stem.with_suffix(".mp3")
    mp3.write_bytes(audio)
    _to_wav(mp3, stem.with_suffix(".wav"))
    return words


def _polly(text, voice, rate, stem: Path) -> list[dict]:
    import boto3
    from xml.sax.saxutils import escape
    polly = boto3.client("polly")
    ssml = f"<speak><prosody rate='{rate or '100%'}'>{escape(text)}</prosody></speak>"
    args = dict(Text=ssml, TextType="ssml", VoiceId=voice or "Matthew", Engine="neural")
    mp3 = stem.with_suffix(".mp3")
    mp3.write_bytes(polly.synthesize_speech(OutputFormat="mp3", **args)["AudioStream"].read())
    _to_wav(mp3, stem.with_suffix(".wav"))
    raw = polly.synthesize_speech(OutputFormat="json", SpeechMarkTypes=["word"], **args)["AudioStream"].read().decode()
    return [{"time": m["time"], "value": m["value"]} for m in map(json.loads, filter(str.strip, raw.splitlines()))]


def _silent(text, voice, rate, stem: Path) -> list[dict]:
    tokens = text.split()
    total = max(1.0, len(tokens) / 2.5)
    run(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{total:.2f}", str(stem.with_suffix(".wav"))])
    chars = sum(len(t) + 1 for t in tokens)
    out, acc = [], 0
    for t in tokens:
        out.append({"time": int(acc / chars * total * 1000), "value": t})
        acc += len(t) + 1
    return out


def _align(tokens: list[str], words: list[dict]) -> list[dict] | None:
    """The written words (with punctuation) matched to the engine's words, which may split or join them."""
    out, i = [], 0
    for tok in tokens:
        target = re.sub(r"\W", "", tok).lower()
        if not target:
            continue
        acc, first = "", i
        while i < len(words) and len(acc) < len(target):
            acc += re.sub(r"\W", "", words[i]["value"]).lower()
            i += 1
        if acc != target:
            return None
        out.append({"time": words[first]["time"], "value": tok})
    return out if i == len(words) else None


def phrases(words: list[dict], dur_ms: int, limit: int = 46) -> list[dict]:
    """Subtitle phrases: break after punctuation or at about `limit` characters (two short lines at most)."""
    groups, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x["value"] for x in cur)
        if (re.search(r"[.,;:!?]$", w["value"]) and len(text) > 14) or len(text) >= limit:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    chunks = []
    for i, grp in enumerate(groups):
        end = groups[i + 1][0]["time"] - 80 if i + 1 < len(groups) else dur_ms + 500
        text = " ".join(x["value"] for x in grp)
        for spoken, written in DISPLAY:
            text = re.sub(spoken, written, text)
        chunks.append({"t": max(0, grp[0]["time"] - 80), "e": end, "text": text})
    return chunks


# =============================================================================================== recording
class Segment:
    """One browser recording. All times are seconds since the recording started (`now()`)."""

    def __init__(self, name: str, page, ctx, clips: dict[str, Clip], t0: float):
        self.name, self.page, self.ctx, self.clips, self.t0 = name, page, ctx, clips, t0
        self.marks: list[tuple[int, str]] = []      # (ms, wav) of every voice clip in this segment
        self.speedups: list[tuple[float, float, float]] = []
        self.start_s = 0.0
        self.end_s: float | None = None
        self.key: str | None = None
        self.beat_t = time.monotonic()

    # ---- time
    def now(self) -> float:
        return time.monotonic() - self.t0

    def beat(self, key: str, *, subtitles: bool = True) -> "Segment":
        """Start narration beat `key`: its audio is placed here, and its subtitles start now."""
        self.key, self.beat_t = key, time.monotonic()
        self.marks.append((int(self.now() * 1000), str(self.clips[key].wav)))
        if subtitles:
            self.ev("a => window.demoSubs(a[0], a[1])", [int(time.time() * 1000), self.clips[key].chunks])
        return self

    def at(self, seconds: float) -> None:
        """Wait until `seconds` after the start of the current beat."""
        wait = self.beat_t + seconds - time.monotonic()
        if wait > 0:
            self.page.wait_for_timeout(int(wait * 1000))

    def finish(self, floor: float = 0.0, tail: float = 0.6) -> None:
        """Wait until the beat's voice has ended (plus `tail`), or `floor` seconds, whichever is later."""
        self.at(max(self.clips[self.key].dur + tail, floor))

    def word_time(self, word: str) -> float | None:
        """Seconds into the current beat at which `word` is first spoken."""
        want = re.sub(r"\W", "", word).lower()
        for w in self.clips[self.key].words:
            if re.sub(r"\W", "", w["value"]).lower().startswith(want):
                return w["time"] / 1000
        return None

    def on_words(self, table: list[tuple[str, object]], lead: float = 0.25) -> None:
        """Run actions as words are spoken: table = [(word, js_string_or_python_callable)], each word once."""
        events = sorted((t - lead, act) for word, act in table if (t := self.word_time(word)) is not None)
        for t, act in events:
            self.at(max(0.0, t))
            self.ev(act) if isinstance(act, str) else act()

    # ---- the page
    def ev(self, expr: str, arg=None):
        """page.evaluate that survives a navigation in progress."""
        for _ in range(8):
            try:
                self.page.wait_for_load_state("domcontentloaded")
                return self.page.evaluate(expr, arg) if arg is not None else self.page.evaluate(expr)
            except Exception as e:
                if "context was destroyed" not in str(e) and "navigation" not in str(e):
                    raise
                self.page.wait_for_timeout(250)
        raise RuntimeError("the page kept navigating")

    def chip(self, text: str) -> None:
        self.ev("t => window.demoChip(t)", text)

    def camera(self, selector: str | None, scale: float = 1.5, settle_ms: int = 1100) -> None:
        self.ev("a => window.demoCamera(a[0], a[1])", [selector, scale])
        self.page.wait_for_timeout(settle_ms)            # let the zoom finish before clicking anything

    def click(self, selector: str, steps: int = 28) -> None:
        """Move the visible cursor to the element, then click (a real mouse click, so the app reacts as for a user)."""
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
        self.page.wait_for_timeout(300)
        self.page.mouse.down()
        self.page.wait_for_timeout(110)
        self.page.mouse.up()

    def type(self, selector: str, text: str, delay_ms: int = 45) -> None:
        self.click(selector)
        self.page.keyboard.type(text, delay=delay_ms)

    # ---- editing marks
    def fast_forward(self, start: float, end: float | None = None, to: float = 1.0) -> None:
        """Play [start, end] (seconds, from now()) in `to` seconds: for waits, loading and typing nobody needs to watch.
        Never fast-forward over narration: the voice would be cut out of sync (check_overlaps warns)."""
        end = self.now() if end is None else end
        if end - start > to + 0.3:
            self.speedups.append((start, end, (end - start) / to))

    def hold(self, seconds: float = 1.8) -> None:
        """Keep the screen still at normal speed, so a viewer can read or pause on the result."""
        self.page.wait_for_timeout(int(seconds * 1000))

    def trim_start(self) -> None:
        """Cut everything recorded before this moment (a slow first page load, a sign-in)."""
        self.start_s = self.now()

    def end_here(self, tail: float = 0.3) -> None:
        """Cut the segment at this moment (plus `tail`)."""
        self.end_s = self.now() + tail


def launch(pw, headless: bool = True):
    """Playwright's own Chromium if installed, otherwise the installed Chrome."""
    try:
        return pw.chromium.launch(headless=headless)
    except Exception:
        return pw.chromium.launch(channel="chrome", headless=headless)


def record_segment(name: str, clips: dict[str, Clip], body, out_dir: Path, *, viewport=(1280, 720),
                   setup=None, init_scripts: tuple[str, ...] = (), headless: bool = True) -> dict:
    """Record one segment: `body(seg)` drives the page. `setup(ctx)` runs before the page opens (sign in through
    ctx.request, set cookies). Writes <out_dir>/<name>.json, which `assemble` reads."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    vid_dir = out_dir / name
    vid_dir.mkdir(exist_ok=True)
    for old in vid_dir.glob("*.webm"):
        old.unlink()
    w, h = viewport
    with sync_playwright() as pw:
        browser = launch(pw, headless)
        ctx = browser.new_context(viewport={"width": w, "height": h}, record_video_dir=str(vid_dir),
                                  record_video_size={"width": w, "height": h})
        if setup:
            setup(ctx)
        page = ctx.new_page()
        page.add_init_script(OVERLAY_JS)
        for js in init_scripts:
            page.add_init_script(js)
        t0 = time.monotonic()
        seg = Segment(name, page, ctx, clips, t0)
        body(seg)
        page.wait_for_timeout(400)
        session_end = time.monotonic() - t0
        video = Path(page.video.path())
        ctx.close()
        browser.close()
    # The video starts at the first painted frame, not at t0: measure the offset from its length (the overlay's
    # ticking pixel keeps frames coming until the end).
    origin = max(0.0, session_end - duration(video))
    info = {"video": str(video), "marks": seg.marks, "speedups": seg.speedups, "start_s": seg.start_s,
            "end_s": seg.end_s if seg.end_s is not None else session_end, "origin_s": origin}
    (out_dir / f"{name}.json").write_text(json.dumps(info), encoding="utf-8")
    print(f"recorded {name}: {info['end_s'] - info['start_s']:.1f}s of session, {len(seg.marks)} voice clips, "
          f"{len(seg.speedups)} fast-forwards")
    return info


# =============================================================================================== assembly
def _remap(t: float, info: dict) -> float:
    """Session time (s) -> time in the cut segment."""
    saved = sum(max(0.0, min(t, e) - max(info["start_s"], s)) * (1 - 1 / f)
                for s, e, f in info["speedups"])
    return t - saved - info["start_s"]


def _wav_len(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def cut_segment(name: str, out_dir: Path, *, fps: int = 30, fade: float = 0.25, size: tuple[int, int] | None = None) -> Path:
    """Trim, fast-forward and fade one segment into <name>.mp4 (no audio)."""
    info = json.loads((out_dir / f"{name}.json").read_text(encoding="utf-8"))
    o = info["origin_s"]
    start, end = info["start_s"], info["end_s"]
    wins = sorted((s, e, f) for s, e, f in info["speedups"] if e > start and s < end)
    pieces, cur = [], start
    for s, e, f in wins:
        s, e = max(s, cur), min(e, end)
        if s > cur:
            pieces.append((cur, s, 1.0))
        pieces.append((s, e, f))
        cur = e
    if cur < end:
        pieces.append((cur, end, 1.0))
    chains = [f"[0:v]trim=start={max(0, a - o):.3f}:end={max(0, b - o):.3f},setpts=(PTS-STARTPTS)/{f:.4f}[v{k}]"
              for k, (a, b, f) in enumerate(pieces)]
    want = _remap(end, info)
    post = f"fps={fps},tpad=stop_mode=clone:stop_duration=30,trim=duration={want:.3f}"   # hold the last frame if short
    if size:
        post += f",scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease,pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2"
    if fade:
        post += f",fade=t=in:st=0:d={fade},fade=t=out:st={max(0, want - fade):.3f}:d={fade}"
    graph = ";".join(chains) + ";" + "".join(f"[v{k}]" for k in range(len(pieces))) + \
        f"concat=n={len(pieces)}:v=1:a=0[c];[c]{post}[out]"
    mp4 = out_dir / f"{name}.mp4"
    run(["-i", info["video"], "-filter_complex", graph, "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "20", "-an", str(mp4)])
    return mp4


def timeline(names: list[str], out_dir: Path) -> tuple[list[tuple[float, float, str, str]], float]:
    """Every voice clip on the final timeline: (start, end, segment, wav), and the total length."""
    clips, offset = [], 0.0
    for name in names:
        info = json.loads((out_dir / f"{name}.json").read_text(encoding="utf-8"))
        for ms, wav in info["marks"]:
            t = ms / 1000
            if t < info["start_s"] - 0.05 or t >= info["end_s"] - 0.2:
                continue                          # starts in a part that was cut away
            a = offset + _remap(t, info)
            clips.append((a, a + _wav_len(wav), name, wav))
        offset += _remap(info["end_s"], info)
    return sorted(clips), offset


def assemble(names: list[str], out_dir: Path, out_path: Path, *, fps: int = 30, fade: float = 0.25,
             size: tuple[int, int] | None = None, music: Path | None = None, music_db: float = -24,
             loudnorm: bool = True) -> Path:
    """Cut every segment, join them, place every voice clip, optionally add quiet music under the voice, and
    normalise loudness to about -16 LUFS (what YouTube plays without turning it down)."""
    problems = check_overlaps(names, out_dir)
    if problems:
        raise ValueError("Fix the segment timeline before assembly: " + "; ".join(problems))
    parts = [cut_segment(n, out_dir, fps=fps, fade=fade, size=size) for n in names]
    listing = out_dir / "concat.txt"
    # Concat paths are relative to the list file, not cwd. Escape apostrophes in Windows user/folder names too.
    entries = [p.resolve().as_posix().replace("'", "'\\''") for p in parts]
    listing.write_text("".join(f"file '{entry}'\n" for entry in entries), encoding="utf-8")
    silent = out_dir / "joined.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(silent)])
    clips, total = timeline(names, out_dir)
    inputs, chains, labels = [], [], []
    for n, (a, _, _, wav) in enumerate(clips, start=1):
        inputs += ["-i", wav]
        ms = int(a * 1000)
        chains.append(f"[{n}:a]adelay={ms}|{ms}[a{n}]")
        labels.append(f"[a{n}]")
    if clips:
        graph = ";".join(chains) + ";" + "".join(labels) + f"amix=inputs={len(clips)}:normalize=0[voice]"
    else:                                         # no narration at all: a silent track, so players still show audio
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=mono"]
        graph = "[1:a]anull[voice]"
        loudnorm = False
    final = "[voice]"
    if music:
        k = len(clips) + 1
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        graph += (f";[voice]asplit=2[v1][v2];[{k}:a]volume={music_db}dB[m];"
                  f"[m][v1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
                  f"[v2][duck]amix=inputs=2:normalize=0[mix]")
        final = "[mix]"
    if loudnorm:
        graph += f";{final}loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        final = "[aout]"
    run(["-i", str(silent), *inputs, "-filter_complex", graph, "-map", "0:v", "-map", final, "-c:v", "copy",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out_path)])
    print(f"wrote {out_path}: {total:.1f}s ({total // 60:.0f}:{total % 60:04.1f}), {out_path.stat().st_size / 1e6:.1f} MB")
    return out_path


# =============================================================================================== checks
def check_overlaps(names: list[str], out_dir: Path) -> list[str]:
    """Report overlapping, fast-forwarded or truncated voices. Empty clips are valid for silent video."""
    problems = []
    clips, total = timeline(names, out_dir)
    for i, (a, b, seg, wav) in enumerate(clips):
        for a2, b2, seg2, wav2 in clips[i + 1:]:
            if a2 < b - 0.05:
                problems.append(f"overlap {b - a2:.2f}s at {a2:.1f}s: {seg}/{Path(wav).name} and {seg2}/{Path(wav2).name}")
    for name in names:
        info = json.loads((out_dir / f"{name}.json").read_text(encoding="utf-8"))
        for ms, wav in info["marks"]:
            a, b = ms / 1000, ms / 1000 + _wav_len(wav)
            if a < info["start_s"] - 0.05 or a >= info["end_s"] - 0.2:
                continue                          # same retained clips as timeline(), not audio cut away entirely
            if _remap(a, info) + _wav_len(wav) > _remap(info["end_s"], info) + 0.05:
                problems.append(f"{name}: voice {Path(wav).name} extends past the scene end")
            for s, e, f in info["speedups"]:
                if max(s, info["start_s"]) < b - 0.05 and min(e, info["end_s"]) > a + 0.05:
                    problems.append(f"{name}: fast-forward {s:.1f}-{e:.1f}s runs over the voice {Path(wav).name}")
    print(f"timeline {total:.1f}s, {len(clips)} voice clips, {len(problems)} problem(s)")
    for p in problems:
        print("  " + p)
    return problems


def contact_sheet(video: Path, times: list[float], out_png: Path, width: int = 640, cols: int = 3) -> Path:
    """Frames at the given times, tiled into one image, to look at the cut without watching it."""
    tmp = out_png.parent / f".{out_png.stem}_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    win_font = Path("C:/Windows/Fonts/arial.ttf")
    font = r"fontfile='C\:/Windows/Fonts/arial.ttf':" if win_font.exists() else ""   # no fontconfig on Windows builds
    for i, t in enumerate(times):
        run(["-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf",
             f"scale={width}:-2,drawtext={font}text='{t:.1f}s':x=8:y=8:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6",
             str(tmp / f"f{i:03d}.png")])
    rows = -(-len(times) // cols)
    run(["-i", str(tmp / "f%03d.png"), "-filter_complex", f"tile={cols}x{rows}:padding=6:color=white", str(out_png)])
    return out_png


# =============================================================================================== slides
def make_slide(path: Path, *, kicker: str, title: str, cards: list[dict] | None = None, note: str = "",
               accent: str = "#e4572e") -> Path:
    """An animated 16:9 slide. cards = [{"big": "17x", "text": "...", "src": "Source, date", "hot": False}]; a "big"
    value that is a plain number counts up. Cards appear one after another (0.9 s apart, see `delay`)."""
    tpl = (ASSETS / "slide.html").read_text(encoding="utf-8")
    out = []
    for i, c in enumerate(cards or []):
        big = html.escape(str(c.get("big", "")))
        num = re.fullmatch(r"(\D*)(\d[\d,]*)(\D*)", big)
        if num:
            big = (f"{num.group(1)}<span data-to='{num.group(2).replace(',', '')}' data-suf='{num.group(3)}'>0</span>")
        out.append(f"<div class='card{' hot' if c.get('hot') else ''}' style='--d:{c.get('delay', 0.6 + 0.9 * i):.2f}s'>"
                   f"<div class=big>{big}</div><div class=txt>{html.escape(c.get('text', ''))}</div>"
                   f"<div class=src>{html.escape(c.get('src', ''))}</div></div>")
    page = (tpl.replace("__KICKER__", html.escape(kicker)).replace("__TITLE__", html.escape(title))
            .replace("__CARDS__", "".join(out)).replace("__NOTE__", html.escape(note)).replace("__ACCENT__", accent))
    path.write_text(page, encoding="utf-8")
    return path


def make_spotlight(path: Path, image: Path, foci: dict[str, tuple], title: str = "") -> Path:
    """A page that shows `image` (a diagram) and can dim everything but one box, ring it, label it and zoom to it.
    foci = {"name": ((x, y, w, h), "label")} in the image's own pixels. In the page: focus('name'), focus('all')."""
    tpl = (ASSETS / "spotlight.html").read_text(encoding="utf-8")
    data = {k: {"box": list(v[0]), "label": v[1]} for k, v in foci.items()}
    page = (tpl.replace("__IMG__", image.resolve().as_uri()).replace("__FOCI__", json.dumps(data))
            .replace("__TITLE__", html.escape(title)))
    path.write_text(page, encoding="utf-8")
    return path


# =============================================================================================== command line
def _main(argv: list[str]) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="demo_kit: assemble, check and inspect a demo video")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assemble")
    a.add_argument("segments", nargs="+")
    a.add_argument("--dir", default="segments")
    a.add_argument("--out", default="demo.mp4")
    a.add_argument("--music")
    a.add_argument("--no-fade", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("segments", nargs="+")
    c.add_argument("--dir", default="segments")
    s = sub.add_parser("sheet")
    s.add_argument("video")
    s.add_argument("times", nargs="+", type=float)
    s.add_argument("--out", default="sheet.png")
    v = sub.add_parser("voices")
    v.add_argument("--lang", default="en-")
    args = ap.parse_args(argv)
    if args.cmd == "assemble":
        assemble(args.segments, Path(args.dir), Path(args.out), fade=0 if args.no_fade else 0.25,
                 music=Path(args.music) if args.music else None)
    elif args.cmd == "check":
        sys.exit(1 if check_overlaps(args.segments, Path(args.dir)) else 0)
    elif args.cmd == "sheet":
        print(contact_sheet(Path(args.video), args.times, Path(args.out)))
    elif args.cmd == "voices":
        import edge_tts
        for vv in asyncio.run(edge_tts.list_voices()):
            if vv["ShortName"].startswith(args.lang):
                print(vv["ShortName"], vv["Gender"])


if __name__ == "__main__":
    _main(sys.argv[1:])

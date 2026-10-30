"""Offline machine check for the personal video tool; silent by default.

It makes a tiny local "app" (a form whose answer takes 9 seconds), then records four segments:
  hook   an animated slide with the problem and numbers
  arch   a diagram with a spotlight that follows the narration
  app    the real app: type, click, fast-forward the wait, hold on the result, a callout and a zoom
  close  a closing slide
and cuts them into demo.mp4, checks the audio and writes a contact sheet.

    python example_demo.py                     # no speech synthesis or voice clips
    python example_demo.py --out <folder>      # keep artifacts outside the contest repo
    python example_demo.py --engine edge       # only if voice was requested; optional dependency/network
"""
import argparse
from pathlib import Path

import demo_kit as K

WORK = Path.home() / ".agents" / "tools" / "mvp-demo" / "example-output"

NARRATION = {
    "hook": "Small shops lose hours every week answering the same three questions. Customers wait, and many give up.",
    "arch": "Here is how it works. The browser sends the question to our server. The server checks the rules, "
            "then answers from the shop's own data.",
    "app_a": "A customer asks when the shop opens on Sunday. The answer takes a few seconds, so we skip ahead.",
    "app_b": "Here it is, with the source it came from.",
    "close": "Open source, and it runs with one command.",
}

APP_HTML = """<!doctype html><meta charset=utf-8><title>Shop helper</title>
<style>body{font:18px system-ui;margin:0;background:#f6f3ee}main{max-width:720px;margin:60px auto;background:#fff;
border-radius:14px;padding:28px 32px;box-shadow:0 4px 18px #0001}input{font:inherit;width:70%;padding:10px;border:1px solid #ccc;
border-radius:8px}button{font:inherit;padding:10px 18px;border:0;border-radius:8px;background:#e4572e;color:#fff}
#answer{margin-top:22px;padding:16px;border-radius:10px;background:#eef6ee;display:none}#busy{margin-top:22px;display:none}
.src{color:#666;font-size:15px;margin-top:6px}</style>
<main><h1>Ask the shop</h1><input id=q placeholder="Your question"> <button id=ask>Ask</button>
<div id=busy>Thinking...</div><div id=answer><b>Sunday: 10:00 to 16:00.</b><div class=src>Source: opening-hours.md, updated 2 Oct</div></div></main>
<script>document.getElementById('ask').onclick=()=>{busy.style.display='block';setTimeout(()=>{busy.style.display='none';
answer.style.display='block'},9000)}</script>"""

DIAGRAM_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='1600' height='700' font-family='Segoe UI,sans-serif'>
<rect width='1600' height='700' fill='#fff'/>
<g font-size='34' text-anchor='middle'>
<rect x='80' y='260' width='320' height='160' rx='20' fill='#e8eefc' stroke='#3b5bdb' stroke-width='4'/><text x='240' y='350'>Browser</text>
<rect x='640' y='260' width='320' height='160' rx='20' fill='#fff1e6' stroke='#e4572e' stroke-width='4'/><text x='800' y='350'>Server + rules</text>
<rect x='1200' y='260' width='320' height='160' rx='20' fill='#eaf7ea' stroke='#2b8a3e' stroke-width='4'/><text x='1360' y='350'>Shop data</text>
</g><g stroke='#555' stroke-width='5' marker-end='url(#a)'><line x1='400' y1='340' x2='630' y2='340'/><line x1='960' y1='340' x2='1190' y2='340'/></g>
<defs><marker id='a' markerWidth='10' markerHeight='10' refX='8' refY='5' orient='auto'><path d='M0,0 L10,5 L0,10 z' fill='#555'/></marker></defs></svg>"""


def main(engine: str = "none", work: Path = WORK) -> None:
    work = work.resolve()
    seg_dir = work / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    (work / "app.html").write_text(APP_HTML, encoding="utf-8")
    (work / "diagram.svg").write_text(DIAGRAM_SVG, encoding="utf-8")
    clips = {} if engine == "none" else {
        k: K.tts(v, engine=engine, cache=work / "voice_cache") for k, v in NARRATION.items()
    }
    for k, c in clips.items():
        print(f"voice {k}: {c.dur:.1f}s, {len(c.chunks)} subtitle phrases")

    hook = K.make_slide(work / "hook.html", kicker="Tool check only", title="Illustrative shop demo",
                        cards=[{"big": "6 h", "text": "a week spent on the same questions", "src": "Example figure, replace with a cited source"},
                               {"big": "40%", "text": "of customers give up after waiting", "src": "Example figure", "hot": True}])
    close = K.make_slide(work / "close.html", kicker="Tool check", title="Recording and assembly complete",
                         cards=[{"big": "1", "text": "command: docker compose up", "src": "github.com/you/your-project"}])
    arch = K.make_spotlight(work / "arch.html", work / "diagram.svg",
                            {"browser": ((80, 260, 320, 160), "The customer"), "server": ((640, 260, 320, 160), "Rules first"),
                             "data": ((1200, 260, 320, 160), "The shop's own data")})

    def slide(seg, key, page, floor):
        seg.page.goto(page.as_uri())
        if clips:
            seg.beat(key, subtitles=engine != "silent")
            seg.finish(floor)
        else:
            seg.hold(floor)

    K.record_segment("hook", clips, lambda s: slide(s, "hook", hook, 3.0), seg_dir)
    K.record_segment("close", clips, lambda s: slide(s, "close", close, 2.0), seg_dir)

    def arch_body(seg):
        seg.page.goto(arch.as_uri())
        seg.page.wait_for_function("window.spotlightReady === true")
        if clips:
            seg.beat("arch", subtitles=engine != "silent")
            seg.on_words([("browser", "focus('browser')"), ("server", "focus('server')"), ("data", "focus('data')")])
            seg.finish(tail=0.2)
        else:
            for focus in ("browser", "server", "data"):
                seg.ev(f"focus('{focus}')")
                seg.hold(1.5)
        seg.ev("focus('all')")
        seg.hold(1.8)                                  # let the zoom-out finish, then a still moment
    K.record_segment("arch", clips, arch_body, seg_dir)

    def app_body(seg):
        seg.page.goto((work / "app.html").as_uri())
        seg.trim_start()                               # the page load is not part of the video
        if clips:
            seg.beat("app_a", subtitles=engine != "silent")
        seg.chip("A customer asks a question")
        seg.type("#q", "When do you open on Sunday?")
        seg.click("#ask")
        if clips:
            seg.finish(tail=0.2)                       # never fast-forward while someone is talking
        waited = seg.now()
        seg.page.wait_for_selector("#answer", state="visible")
        seg.fast_forward(waited, to=0.8)               # whatever is left of the wait plays in 0.8 s
        if clips:
            seg.beat("app_b", subtitles=engine != "silent")
        seg.chip("The answer, with its source")
        seg.camera("#answer", 1.6)
        if clips:
            seg.finish(tail=0.3)
        seg.hold(1.8)                                  # a still moment to read or pause on
        seg.camera(None)
        seg.end_here()
    K.record_segment("app", clips, app_body, seg_dir)

    names = ["hook", "arch", "app", "close"]
    out = K.assemble(names, seg_dir, work / "demo.mp4")
    if K.check_overlaps(names, seg_dir):
        raise RuntimeError("The example has timeline problems")
    total = K.duration(out)
    K.contact_sheet(out, [round(total * f, 1) for f in (0.05, 0.2, 0.35, 0.5, 0.62, 0.72, 0.8, 0.88, 0.97)], work / "sheet.png")
    print("contact sheet:", work / "sheet.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="none", choices=["none", "silent", "edge", "polly"])
    ap.add_argument("--out", type=Path, default=WORK)
    args = ap.parse_args()
    main(args.engine, args.out)

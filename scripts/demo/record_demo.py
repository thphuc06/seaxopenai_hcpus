"""Silent 720p storyboard takes using the exact E2E scene functions.

--all --engine none records one WebM per scene. A failed take is named FAIL,
never promoted to a finished demo. P4 owns assembly/callouts/final export.
Official video API: https://playwright.dev/python/docs/videos (2026-10-31).
Prepared-before-event tooling lives in _outside-repo/skills/mvp-demo; this
contest recorder uses Playwright directly and requests no speech dependency.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from e2e import Journey, ROOT, SCENES, preflight, require
from playwright.sync_api import Error as BrowserError, sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--all', action='store_true')
    selection.add_argument('--scene', type=int, choices=range(1, 10))
    parser.add_argument('--engine', choices=['none'], default='none')
    parser.add_argument('--base', default='http://127.0.0.1:5173')
    parser.add_argument('--api', default='http://127.0.0.1:8000/api')
    parser.add_argument('--out', type=Path, default=ROOT / 'scripts/demo/out/recordings')
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--exclusive-slot', action='store_true')
    args = parser.parse_args()
    try:
        preflight(args.base, args.api)
        print('PASS preflight: replay recording, engine none')
        if args.preflight_only:
            return 0
        require(args.exclusive_slot, 'Reserve the Local run slot and pass --exclusive-slot; no reset performed')
        selected = SCENES if args.all else (SCENES[args.scene - 1],)
        take_dir = args.out / uuid4().hex
        take_dir.mkdir(parents=True, exist_ok=True)
        failures = 0
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for scene in selected:
                    context = browser.new_context(viewport={'width': 1280, 'height': 720},
                        record_video_dir=str(take_dir), record_video_size={'width': 1280, 'height': 720})
                    page = context.new_page()
                    page.set_default_timeout(10_000)
                    video = page.video
                    status = 'PASS'
                    try:
                        journey = Journey(page, args.base.rstrip('/'), args.api.rstrip('/'), take_dir / scene.__name__ / 'screenshots')
                        scene(journey)
                        journey.capture(scene.__name__)
                        # Recording-only reading hold; E2E synchronization never depends on sleeps.
                        page.wait_for_timeout(3000)
                    except (AssertionError, BrowserError, KeyError, TypeError, ValueError) as error:
                        failures += 1
                        status = 'FAIL'
                        print(f'FAIL {scene.__name__}: {error}', flush=True)
                    finally:
                        context.close()
                    require(video is not None, 'Playwright did not create a video')
                    # Retain each original take; never overwrite an earlier recording.
                    original = video.path()
                    target = original.with_name(f'{scene.__name__}-{status}-{original.name}')
                    original.rename(target)
                    print(f'{status} {scene.__name__}: {target}', flush=True)
            finally:
                browser.close()
        return int(failures > 0)
    except (AssertionError, BrowserError) as error:
        print(f'FAIL preflight: {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

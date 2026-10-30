"""Offline regression tests for the personal video tool (not contest app tests)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave

import demo_kit as K


class DemoKitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mvp-demo-tests-")
        self.root = Path(self.temp.name).resolve()
        self.assertEqual(self.root.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)

    def wav(self, seconds: float) -> Path:
        path = self.root / "voice.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"\0\0" * round(24000 * seconds))
        return path

    def scene(self, name: str, seconds: float, marks: list | None = None,
              speedups: list | None = None) -> None:
        info = {"video": "unused.webm", "marks": marks or [], "speedups": speedups or [],
                "start_s": 0.0, "end_s": seconds, "origin_s": 0.0}
        (self.root / f"{name}.json").write_text(json.dumps(info), encoding="utf-8")

    def problems(self, names: list[str]) -> list[str]:
        with contextlib.redirect_stdout(io.StringIO()):
            return K.check_overlaps(names, self.root)

    def test_alignment_preserves_punctuation_and_vietnamese(self) -> None:
        words = [{"time": 0, "value": "Mỹ"}, {"time": 500, "value": "phẩm"}]
        self.assertEqual(K._align(["Mỹ", "phẩm."], words),
                         [{"time": 0, "value": "Mỹ"}, {"time": 500, "value": "phẩm."}])

    def test_alignment_rejects_different_content(self) -> None:
        self.assertIsNone(K._align(["cat"], [{"time": 0, "value": "dog"}]))

    def test_empty_subtitles(self) -> None:
        self.assertEqual(K.phrases([], 1000), [])

    def test_fast_forward_remaps_timeline(self) -> None:
        info = {"start_s": 2.0, "speedups": [(4.0, 8.0, 4.0)]}
        self.assertEqual(K._remap(4.0, info), 2.0)
        self.assertEqual(K._remap(10.0, info), 5.0)

    def test_speedup_before_trim_does_not_shorten_retained_scene(self) -> None:
        info = {"start_s": 2.0, "speedups": [(0.0, 1.0, 2.0)]}
        self.assertEqual(K._remap(4.0, info), 2.0)

    def test_silent_segments_have_no_voice_problems(self) -> None:
        self.scene("silent", 2.0)
        self.assertEqual(self.problems(["silent"]), [])

    def test_default_tts_engine_is_offline_silence(self) -> None:
        clip = K.tts("Offline timing only", cache=self.root / "cache")
        with wave.open(str(clip.wav)) as handle:
            self.assertFalse(any(handle.readframes(handle.getnframes())))
        self.assertGreater(clip.dur, 0)

    def test_overlapping_voices_are_reported(self) -> None:
        voice = str(self.wav(1.0))
        self.scene("overlap", 3.0, [[0, voice], [500, voice]])
        self.assertTrue(self.problems(["overlap"]))

    def test_fast_forward_under_voice_is_reported(self) -> None:
        voice = str(self.wav(2.0))
        self.scene("speed", 4.0, [[0, voice]], [[1.0, 3.0, 2.0]])
        self.assertTrue(self.problems(["speed"]))

    def test_voice_past_video_end_is_reported(self) -> None:
        voice = str(self.wav(3.0))
        self.scene("short", 1.0, [[0, voice]])
        self.assertTrue(self.problems(["short"]))

    def test_voice_past_scene_end_is_reported_even_if_video_is_longer(self) -> None:
        voice = str(self.wav(3.0))
        self.scene("short", 1.0, [[0, voice]])
        self.scene("next", 4.0)
        self.assertTrue(self.problems(["short", "next"]))

    def test_voice_entirely_trimmed_out_does_not_block_cut(self) -> None:
        voice = str(self.wav(1.0))
        self.scene("trim", 4.0, [[0, voice]], [[0.0, 1.0, 2.0]])
        path = self.root / "trim.json"
        info = json.loads(path.read_text(encoding="utf-8"))
        info["start_s"] = 2.0
        path.write_text(json.dumps(info), encoding="utf-8")
        self.assertEqual(self.problems(["trim"]), [])

    def test_relative_segment_directory_assembles_without_narration(self) -> None:
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        folder = Path("a user's segments")
        folder.mkdir()
        source = folder.resolve() / "source.mp4"
        K.run(["-f", "lavfi", "-i", "color=c=navy:s=160x90:r=10:d=1", "-c:v", "libx264",
               "-pix_fmt", "yuv420p", str(source)])
        info = {"video": str(source), "marks": [], "speedups": [],
                "start_s": 0.0, "end_s": 1.0, "origin_s": 0.0}
        (folder / "scene.json").write_text(json.dumps(info), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            output = K.assemble(["scene"], folder, Path("demo.mp4"), fps=10, fade=0)
        self.assertTrue(output.is_file())
        self.assertAlmostEqual(K.duration(output), 1.0, delta=0.15)
        probe = subprocess.run([K.FF, "-i", str(output)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", check=False)
        self.assertIn("Video: h264", probe.stderr)
        self.assertIn("Audio: aac", probe.stderr)


if __name__ == "__main__":
    unittest.main()

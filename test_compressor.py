# /// script
# requires-python = ">=3.10"
# dependencies = ["imageio-ffmpeg==0.6.0", "av>=14,<18"]
# ///
"""整合驗證：uv run test_compressor.py"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import av
import imageio_ffmpeg

SCRIPT = Path(__file__).with_name("compress_videos.py")
os.environ["PYTHONUTF8"] = "1"


def audio_packets(path):
    with av.open(str(path)) as container:
        return [hashlib.sha256(bytes(p)).hexdigest() for p in container.demux(audio=0) if p.size]


def frames(path):
    # framemd5 uses only active image pixels, ignoring padded plane memory.
    result = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path),
        "-map", "0:v:0", "-f", "framemd5", "-",
    ], capture_output=True, text=True, check=True)
    return [line.rsplit(",", 1)[-1].strip() for line in result.stdout.splitlines() if line and not line.startswith("#")]


class IntegrationTest(unittest.TestCase):
    def test_quality_lossless_audio_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "中文 含空格.mov"
            subprocess.run([
                imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=12",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "2", "-c:v", "libx264", "-c:a", "aac", str(source),
            ], check=True)
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            for extra in ([], ["--lossless"]):
                command = [sys.executable, str(SCRIPT), str(source), "-o", str(root / "out"), "--preset", "fast", *extra]
                subprocess.run(command, check=True, capture_output=True)
                mode = "lossless" if extra else "crf23"
                target = root / "out" / f"{source.name}.h265-{mode}-fast.mp4"
                self.assertEqual(audio_packets(source), audio_packets(target))
                if extra:
                    self.assertEqual(frames(source), frames(target))
                before = target.stat().st_mtime_ns
                again = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
                self.assertIn("略過", again.stdout)
                self.assertEqual(before, target.stat().st_mtime_ns)
                receipt = target.with_suffix(".mp4.json")
                receipt.unlink()
                conflict = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
                self.assertNotEqual(0, conflict.returncode)
                self.assertEqual(before, target.stat().st_mtime_ns)
            self.assertEqual(original, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertFalse(list(root.rglob("*.partial*")))

    def test_mixed_mov_mp4_default_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mov, mp4 = root / "同名 中文.mov", root / "同名 中文.MP4"
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=320x240:rate=12", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000", "-t", "1",
                            "-c:v", "libx264", "-c:a", "aac", str(mov)], check=True)
            subprocess.run([ffmpeg, "-v", "error", "-i", str(mov), "-c", "copy", str(mp4)], check=True)
            # Generated outputs moved into the source folder must not become inputs.
            (root / "舊成品.mov.h265-crf23-slow.mp4").write_bytes(b"not an input")
            originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (mov, mp4)}
            command = [sys.executable, str(SCRIPT), str(root)]
            subprocess.run(command, check=True, capture_output=True)
            outputs = list((root / "compressed").glob("*.mp4"))
            self.assertEqual(len(outputs), 2)
            for source in (mov, mp4):
                target = root / "compressed" / f"{source.name}.h265-crf23-slow.mp4"
                with av.open(str(target)) as container:
                    self.assertEqual(container.streams.video[0].codec_context.name, "hevc")
                    self.assertEqual(container.streams.video[0].codec_context.width, 320)
                self.assertEqual(audio_packets(source), audio_packets(target))
                self.assertEqual(originals[source], hashlib.sha256(source.read_bytes()).hexdigest())
            again = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(again.stdout.count("已完成且來源與設定相符，略過"), 2)


if __name__ == "__main__":
    unittest.main()

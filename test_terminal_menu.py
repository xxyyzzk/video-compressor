# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
import contextlib
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import terminal_menu as menu


class MenuTests(unittest.TestCase):
    def test_paths_selection_and_output_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first, second = root / "含 空格 (課程)", root / "其他課程"
            first.mkdir()
            second.mkdir()
            mov, mp4 = first / "同名.mov", first / "同名.MP4"
            for path in [mov, mp4, first / "旧.mov.h265-crf23-slow.mp4"]:
                path.touch()
            with patch.multiple(menu, SOURCE=menu.SOURCE, OUTPUT=menu.OUTPUT):
                menu.configure(first)
                self.assertEqual(set(menu.source_files()), {mov, mp4})
                self.assertEqual(menu.parse_path('"' + str(mp4) + '"'), mp4)
                self.assertEqual(menu.parse_path(str(first)), first)
                if os.name != "nt":
                    self.assertEqual(menu.parse_path(shlex.quote(str(first))), first)
                with patch("builtins.input", side_effect=["p", '"' + str(mp4) + '"', "1", "q"]), \
                        patch.object(menu, "run_one", return_value=0) as run, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(menu.menu(), 0)
                    run.assert_called_once_with(mp4)
                self.assertEqual(menu.OUTPUT, first / "compressed")
                menu.configure(second)
                self.assertEqual(menu.OUTPUT, second / "compressed")
                with self.assertRaises(ValueError):
                    menu.configure(root / "missing.mp4")
                self.assertEqual(menu.SOURCE, second)

    def test_startup_selection_cancel_and_explicit_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.multiple(menu, BASE=root, SOURCE=menu.SOURCE, OUTPUT=menu.OUTPUT), \
                    contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys, "argv", ["terminal_menu.py"]), \
                        patch.object(menu, "pick_folder", return_value=root), \
                        patch.object(menu, "menu", return_value=0) as shown:
                    self.assertEqual(menu.main(), 0)
                    shown.assert_called_once()
                    self.assertEqual(menu.SOURCE, root)
                with patch.object(sys, "argv", ["terminal_menu.py"]), \
                        patch.object(menu, "pick_folder", return_value=None), \
                        patch.object(menu, "menu") as shown:
                    self.assertEqual(menu.main(), 0)
                    shown.assert_not_called()
                with patch.object(sys, "argv", ["terminal_menu.py", str(root)]), \
                        patch.object(menu, "pick_folder") as picker, \
                        patch.object(menu, "menu", return_value=0):
                    self.assertEqual(menu.main(), 0)
                    picker.assert_not_called()

    def test_unavailable_dialog_falls_back_to_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.multiple(menu, SOURCE=menu.SOURCE, OUTPUT=menu.OUTPUT), \
                    patch.object(menu, "pick_folder", side_effect=RuntimeError("No desktop")), \
                    patch("builtins.input", return_value=str(root)), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(menu.select_source())
                self.assertEqual(menu.SOURCE, root)

    def test_lock_across_processes_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "menu.lock"
            command = [sys.executable, "-c", (
                "import sys; from terminal_menu import acquire_lock; "
                "f=open(sys.argv[1], 'a+b'); acquire_lock(f)"
            ), str(path)]
            with path.open("a+b") as lock:
                menu.acquire_lock(lock)
                busy = subprocess.run(command, cwd=menu.BASE, capture_output=True)
                self.assertNotEqual(busy.returncode, 0)
            available = subprocess.run(command, cwd=menu.BASE, capture_output=True)
            self.assertEqual(available.returncode, 0, available.stderr)


if __name__ == "__main__":
    unittest.main()

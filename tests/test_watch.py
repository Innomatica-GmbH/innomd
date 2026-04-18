"""Unit tests for watch-mode helpers (pure, non-interactive)."""
import unittest

from conftest import load_innomd

innomd = load_innomd()


class TestAnsiStrip(unittest.TestCase):
    def test_removes_sgr(self):
        self.assertEqual(innomd._ansi_strip("\x1b[31mred\x1b[0m"), "red")

    def test_removes_cursor_sequences(self):
        self.assertEqual(innomd._ansi_strip("\x1b[2J\x1b[Hhi"), "hi")

    def test_removes_sgr_with_multiple_params(self):
        self.assertEqual(innomd._ansi_strip("\x1b[1;31;4mbold\x1b[0m"), "bold")

    def test_preserves_plain_text(self):
        self.assertEqual(innomd._ansi_strip("no escapes here"), "no escapes here")


class TestClampOffset(unittest.TestCase):
    def _mk(self, lines=50, rows=20, offset=0):
        s = innomd._WatchState("/tmp/x.md", None, "default", None)
        s.lines = ["x"] * lines
        s.rows = rows
        s.offset = offset
        return s

    def test_clamps_negative(self):
        s = self._mk(offset=-5)
        innomd._clamp_offset(s)
        self.assertEqual(s.offset, 0)

    def test_clamps_past_end(self):
        s = self._mk(lines=50, rows=20, offset=100)
        innomd._clamp_offset(s)
        # body_rows = rows-1 = 19; max_offset = 50-19 = 31
        self.assertEqual(s.offset, 31)

    def test_short_file_forces_zero(self):
        s = self._mk(lines=5, rows=20, offset=10)
        innomd._clamp_offset(s)
        self.assertEqual(s.offset, 0)


class TestStatusLine(unittest.TestCase):
    def test_contains_filename_and_position(self):
        s = innomd._WatchState("/tmp/hello.md", None, "nord", None)
        s.lines = ["a"] * 100
        s.cols = 120
        s.rows = 25
        s.offset = 10
        out = innomd._status_line(s)
        self.assertIn("hello.md", out)
        self.assertIn("nord", out)
        self.assertIn("11-", out)  # offset+1
        self.assertIn("/100", out)

    def test_truncates_to_cols(self):
        s = innomd._WatchState("/tmp/long-name-file.md", None, "default", None)
        s.lines = ["x"] * 10
        s.cols = 40
        s.rows = 25
        out = innomd._status_line(s)
        self.assertLessEqual(len(out), 40)


if __name__ == "__main__":
    unittest.main()

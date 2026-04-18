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


class TestHighlightMatches(unittest.TestCase):
    def test_highlights_plain(self):
        import re
        pat = re.compile("bar")
        out = innomd._highlight_matches("foo bar baz", pat)
        self.assertIn("\x1b[7m", out)
        self.assertIn("\x1b[27m", out)
        self.assertIn("bar", out)

    def test_no_match_returns_line_unchanged(self):
        import re
        pat = re.compile("zzz")
        line = "\x1b[31mred text\x1b[0m"
        self.assertEqual(innomd._highlight_matches(line, pat), line)

    def test_highlights_inside_ansi(self):
        import re
        pat = re.compile("world")
        line = "\x1b[1mhello world\x1b[0m"
        out = innomd._highlight_matches(line, pat)
        # original ANSI codes preserved
        self.assertIn("\x1b[1m", out)
        self.assertIn("\x1b[0m", out)
        # highlight opens before match and closes at/after end-of-match
        self.assertIn("\x1b[7mworld", out)
        self.assertIn("\x1b[27m", out)
        # reverse-on sits between the opening bold and the match
        self.assertLess(out.index("\x1b[7m"), out.index("world"))


class TestSearch(unittest.TestCase):
    def _mk_state(self):
        s = innomd._WatchState("/tmp/x.md", None, "default", None)
        s.lines = ["apple", "banana", "cherry", "banana split", "date"]
        s.cols = 80
        s.rows = 3  # body_rows = 2, so offsets up to 3 are reachable
        return s

    def test_search_populates_matches(self):
        s = self._mk_state()
        innomd._do_search(s, "banana")
        self.assertEqual(s.match_lines, [1, 3])

    def test_search_no_match(self):
        s = self._mk_state()
        innomd._do_search(s, "zzz")
        self.assertEqual(s.match_lines, [])
        self.assertIn("no match", s.status_msg)

    def test_empty_pattern_clears(self):
        s = self._mk_state()
        innomd._do_search(s, "banana")
        innomd._do_search(s, "")
        self.assertIsNone(s.search_pattern)
        self.assertEqual(s.match_lines, [])

    def test_bad_regex_sets_status(self):
        s = self._mk_state()
        innomd._do_search(s, "(unclosed")
        self.assertIsNone(s.search_pattern)
        self.assertIn("bad regex", s.status_msg)

    def test_search_is_case_insensitive(self):
        s = self._mk_state()
        innomd._do_search(s, "APPLE")
        self.assertEqual(s.match_lines, [0])

    def test_jump_to_next_cycles(self):
        s = self._mk_state()
        innomd._do_search(s, "banana")
        # first match is line 1, jumps there
        self.assertEqual(s.offset, 1)
        with s.lock:
            innomd._jump_to_match(s, forward=True)
        self.assertEqual(s.offset, 3)
        with s.lock:
            innomd._jump_to_match(s, forward=True)
        self.assertEqual(s.offset, 1)  # wraps

    def test_jump_to_prev(self):
        s = self._mk_state()
        innomd._do_search(s, "banana")
        # after initial jump, offset = 1
        with s.lock:
            innomd._jump_to_match(s, forward=False)
        self.assertEqual(s.offset, 3)  # wraps backward


class TestPromptKeys(unittest.TestCase):
    def _mk(self):
        s = innomd._WatchState("/tmp/x.md", None, "default", None)
        s.lines = ["one", "two", "three"]
        s.cols, s.rows = 80, 24
        return s

    def test_slash_enters_prompt(self):
        s = self._mk()
        innomd._handle_key(s, "/")
        self.assertEqual(s.mode, "prompt")
        self.assertEqual(s.prompt_prefix, "/")

    def test_colon_enters_prompt(self):
        s = self._mk()
        innomd._handle_key(s, ":")
        self.assertEqual(s.mode, "prompt")
        self.assertEqual(s.prompt_prefix, ":")

    def test_prompt_types_and_submits_search(self):
        s = self._mk()
        innomd._handle_key(s, "/")
        for c in "two":
            innomd._handle_key(s, c)
        self.assertEqual(s.prompt_buffer, "two")
        innomd._handle_key(s, "\r")
        self.assertEqual(s.mode, "normal")
        self.assertEqual(s.match_lines, [1])

    def test_prompt_backspace(self):
        s = self._mk()
        innomd._handle_key(s, "/")
        for c in "tax":
            innomd._handle_key(s, c)
        innomd._handle_key(s, "\x7f")
        self.assertEqual(s.prompt_buffer, "ta")

    def test_prompt_escape_cancels(self):
        s = self._mk()
        innomd._handle_key(s, "/")
        innomd._handle_key(s, "x")
        innomd._handle_key(s, "\x1b")
        self.assertEqual(s.mode, "normal")
        self.assertEqual(s.prompt_buffer, "")

    def test_colon_q_quits(self):
        s = self._mk()
        innomd._handle_key(s, ":")
        innomd._handle_key(s, "q")
        action = innomd._handle_key(s, "\r")
        self.assertEqual(action, "quit")

    def test_colon_unknown_sets_status(self):
        s = self._mk()
        innomd._handle_key(s, ":")
        for c in "foo":
            innomd._handle_key(s, c)
        innomd._handle_key(s, "\r")
        self.assertIn("unknown", s.status_msg)


if __name__ == "__main__":
    unittest.main()

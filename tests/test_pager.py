"""Tests for the built-in pager invocation in render_once()."""
import os
import re
import unittest
from unittest import mock

from conftest import load_innomd

innomd = load_innomd()

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def page(text, *, wide=False, source_name="doc.md", env=None):
    """Run render_once() with the pager path, capturing less's argv and input."""
    captured = {}

    def fake_run(argv, *args, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        with open(argv[-1], encoding="utf-8") as f:
            captured["lines"] = ANSI.sub("", f.read()).split("\n")

    with mock.patch.object(innomd.subprocess, "run", fake_run), \
         mock.patch.object(innomd.shutil, "get_terminal_size",
                           return_value=os.terminal_size((80, 24))), \
         mock.patch.dict(os.environ, env or {}):
        innomd.render_once(text, None, "default", None, True,
                           diagrams_wide=wide, source_name=source_name)
    return captured


class TestPagerInvocation(unittest.TestCase):
    def test_runs_less_directly_ignoring_manpager(self):
        # A filtering MANPAGER (col -b) strips ANSI escapes; it must not
        # be consulted for innomd's output.
        c = page("# hi", env={"MANPAGER": "sh -c 'col -bx | cat'",
                              "PAGER": "more"})
        self.assertEqual(c["argv"][0], "less")

    def test_flags_passed_on_command_line_not_via_env(self):
        # A user's own $LESS must not replace -R, or colour codes show
        # up as literal `ESC[...` text.
        c = page("# hi", env={"LESS": "-F"})
        self.assertIn("-R", c["argv"])
        self.assertNotIn("env", c["kwargs"])

    def test_no_chop_without_diagrams_wide(self):
        c = page("# hi")
        self.assertNotIn("-S", c["argv"])

    def test_chop_with_diagrams_wide(self):
        c = page("# hi", wide=True)
        self.assertIn("-S", c["argv"])

    def test_prompt_escapes_filename_metacharacters(self):
        c = page("# hi", source_name="/tmp/a.b?c:d%e.md")
        prompt = next(a for a in c["argv"] if a.startswith("-P"))
        self.assertIn(r"a\.b\?c\:d\%e\.md", prompt)


class TestWideCodeBlocks(unittest.TestCase):
    LONG = "x" * 150 + "END"

    def test_code_block_not_wrapped_when_wide(self):
        c = page("```\n" + self.LONG + "\n```\n", wide=True)
        self.assertTrue(any(self.LONG in ln for ln in c["lines"]))

    def test_code_block_wraps_by_default(self):
        c = page("```\n" + self.LONG + "\n```\n")
        self.assertFalse(any(self.LONG in ln for ln in c["lines"]))
        self.assertTrue(all(len(ln) <= 80 for ln in c["lines"]))

    def test_prose_still_wraps_when_wide(self):
        c = page("word " * 60, wide=True)
        self.assertTrue(all(len(ln) <= 80 for ln in c["lines"]))

    def test_wide_diagram_keeps_full_rows(self):
        src = ("```mermaid\nflowchart LR\n"
               "  A[Alpha start node] --> B[Bravo second node] --> "
               "C[Charlie third node] --> D[Delta fourth node] --> "
               "E[Echo fifth node] --> F[Foxtrot end]\n```\n")
        text = innomd.preprocess(src, diagram_width=80, diagrams_wide=True)
        c = page(text, wide=True)
        row = next(ln for ln in c["lines"] if "Alpha start node" in ln)
        self.assertIn("Foxtrot end", row)


if __name__ == "__main__":
    unittest.main()

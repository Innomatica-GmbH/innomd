"""End-to-end tests that actually run the innomd CLI."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

INNOMD = Path(__file__).resolve().parent.parent / "innomd"


def run(args, input_text=None, env=None, timeout=10):
    proc_env = os.environ.copy()
    proc_env.setdefault("TERM", "xterm-256color")
    proc_env.setdefault("NO_COLOR", "1")  # plain output, easier to assert on
    proc_env.setdefault("COLUMNS", "100")
    if env:
        proc_env.update(env)
    result = subprocess.run(
        ["python3", str(INNOMD), *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=proc_env,
    )
    return result


class TestCLI(unittest.TestCase):
    def test_help_exits_zero(self):
        r = run(["--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("usage:", r.stdout.lower())

    def test_version_exits_zero(self):
        r = run(["--version"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("innomd", r.stdout)
        # semver-ish: N.N.N somewhere
        import re as _re
        self.assertRegex(r.stdout, r"\d+\.\d+\.\d+")

    def test_list_themes(self):
        r = run(["--list-themes"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("dracula", r.stdout)
        self.assertIn("nord", r.stdout)
        self.assertIn("default", r.stdout)

    def test_unknown_theme_errors(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("# hi")
            path = f.name
        try:
            r = run(["--no-pager", "-t", "nonsense", path])
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("unknown theme", r.stderr)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        r = run(["--no-pager", "/tmp/does-not-exist-xyz.md"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("file not found", r.stderr.lower())


class TestRendering(unittest.TestCase):
    def _render(self, md, args=()):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(md)
            path = f.name
        try:
            r = run(["--no-pager", "-w", "100", *args, path])
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            return r.stdout
        finally:
            os.unlink(path)

    def test_math_block_rendered(self):
        out = self._render(r"$$\lambda = \frac{b}{T}$$")
        self.assertIn("λ = b/T", out)

    def test_inline_math(self):
        out = self._render("Inline $x^2$ done.")
        self.assertIn("x²", out)

    def test_table_has_borders(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        out = self._render(md)
        # rounded-border table drawing characters
        self.assertTrue(any(ch in out for ch in "╭╮╰╯"))

    def test_horizontal_rule_is_compact(self):
        out = self._render("# A\n\n---\n\n# B\n")
        self.assertIn("· · ·", out)
        # ensure we don't get a full-width dash line
        self.assertNotIn("-" * 60, out)

    def test_code_block_math_not_converted(self):
        md = "```\n$$E = mc^2$$\n```\n"
        out = self._render(md)
        self.assertIn("$$E = mc^2$$", out)

    def test_theme_renders_without_error(self):
        for theme in ("default", "dracula", "nord", "gruvbox",
                      "solarized-dark", "solarized-light", "tokyonight",
                      "github", "mono"):
            out = self._render("# Hi\n\n$$a+b$$", args=("-t", theme))
            self.assertIn("Hi", out, msg=f"theme {theme} failed")
            self.assertIn("a+b", out, msg=f"theme {theme} failed")


class TestStdin(unittest.TestCase):
    def test_pipe_stdin(self):
        r = run(["--no-pager", "-w", "80"],
                input_text="# Hello\n\n$$x^2$$\n")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("Hello", r.stdout)
        self.assertIn("x²", r.stdout)

    def test_raw_mode_emits_preprocessed_markdown(self):
        r = run(["--raw"], input_text=r"$$x^2$$" + "\n")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("x²", r.stdout)
        # preprocess wraps display math in a blockquote
        self.assertIn(">", r.stdout)


class TestIpynbE2E(unittest.TestCase):
    def test_notebook_file(self):
        nb = {
            "cells": [
                {"cell_type": "markdown", "metadata": {},
                 "source": ["# Notebook\n\n", "Text with $x^2$."]},
                {"cell_type": "code", "execution_count": 1,
                 "metadata": {},
                 "outputs": [{"output_type": "stream",
                              "name": "stdout", "text": ["42\n"]}],
                 "source": ["print(42)"]},
            ],
            "metadata": {"kernelspec": {"language": "python", "name": "py"}},
            "nbformat": 4, "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile("w", suffix=".ipynb", delete=False) as f:
            json.dump(nb, f)
            path = f.name
        try:
            r = run(["--no-pager", "-w", "100", path])
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            self.assertIn("Notebook", r.stdout)
            self.assertIn("x²", r.stdout)
            self.assertIn("print(42)", r.stdout)
            self.assertIn("42", r.stdout)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

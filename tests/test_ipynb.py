"""Unit tests for Jupyter notebook conversion."""
import json
import unittest

from conftest import load_innomd

innomd = load_innomd()
ipynb_to_markdown = innomd.ipynb_to_markdown


def notebook(cells, language="python"):
    return json.dumps({
        "cells": cells,
        "metadata": {"kernelspec": {"language": language, "name": "py"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    })


class TestNotebookConversion(unittest.TestCase):
    def test_markdown_cell(self):
        nb = notebook([{"cell_type": "markdown", "metadata": {},
                        "source": ["# Hello\n", "\n", "Body"]}])
        out = ipynb_to_markdown(nb)
        self.assertIn("# Hello", out)
        self.assertIn("Body", out)

    def test_code_cell_uses_kernel_language(self):
        nb = notebook([{"cell_type": "code", "execution_count": 1,
                        "metadata": {}, "outputs": [],
                        "source": ["print('hi')"]}], language="python")
        out = ipynb_to_markdown(nb)
        self.assertIn("```python", out)
        self.assertIn("print('hi')", out)

    def test_stream_output_emitted(self):
        nb = notebook([{"cell_type": "code", "execution_count": 1,
                        "metadata": {},
                        "outputs": [{"output_type": "stream",
                                     "name": "stdout",
                                     "text": ["Hello\n", "42\n"]}],
                        "source": ["print('Hello')"]}])
        out = ipynb_to_markdown(nb)
        self.assertIn("Hello", out)
        self.assertIn("42", out)
        # stream output becomes a fenced block too
        self.assertGreaterEqual(out.count("```"), 4)

    def test_execute_result_plain_text(self):
        nb = notebook([{"cell_type": "code", "execution_count": 1,
                        "metadata": {},
                        "outputs": [{"output_type": "execute_result",
                                     "execution_count": 1,
                                     "metadata": {},
                                     "data": {"text/plain": ["42"]}}],
                        "source": ["40 + 2"]}])
        out = ipynb_to_markdown(nb)
        self.assertIn("40 + 2", out)
        self.assertIn("42", out)

    def test_markdown_output_preserved(self):
        nb = notebook([{"cell_type": "code", "execution_count": 1,
                        "metadata": {},
                        "outputs": [{"output_type": "display_data",
                                     "metadata": {},
                                     "data": {"text/markdown":
                                              ["# From cell\n"]}}],
                        "source": ["show_md()"]}])
        out = ipynb_to_markdown(nb)
        self.assertIn("# From cell", out)

    def test_error_output_strips_ansi(self):
        nb = notebook([{"cell_type": "code", "execution_count": 1,
                        "metadata": {},
                        "outputs": [{"output_type": "error",
                                     "ename": "ValueError", "evalue": "x",
                                     "traceback": ["\x1b[0;31mBoom\x1b[0m"]}],
                        "source": ["raise ValueError('x')"]}])
        out = ipynb_to_markdown(nb)
        self.assertIn("Boom", out)
        self.assertNotIn("\x1b[", out)

    def test_raw_cell(self):
        nb = notebook([{"cell_type": "raw", "metadata": {},
                        "source": ["literal text"]}])
        out = ipynb_to_markdown(nb)
        self.assertIn("literal text", out)


if __name__ == "__main__":
    unittest.main()

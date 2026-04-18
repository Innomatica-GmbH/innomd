"""Unit tests for the Markdown preprocessing step."""
import unittest

from conftest import load_innomd

innomd = load_innomd()
preprocess = innomd.preprocess


class TestBlockMath(unittest.TestCase):
    def test_double_dollar(self):
        out = preprocess(r"Intro $$E = mc^2$$ end.")
        self.assertIn("E = mc²", out)
        self.assertIn(">", out)  # rendered as blockquote

    def test_bracket_display(self):
        out = preprocess(r"Before \[a + b\] after.")
        self.assertIn("a + b", out)
        self.assertIn(">", out)

    def test_multiline_block(self):
        src = "Before\n\n$$\n\\lambda = \\frac{b}{T}\n$$\n\nAfter"
        out = preprocess(src)
        self.assertIn("λ = b/T", out)


class TestInlineMath(unittest.TestCase):
    def test_inline_dollar(self):
        out = preprocess(r"text $x^2$ more")
        self.assertIn("`x²`", out)

    def test_inline_paren(self):
        out = preprocess(r"Let \(x = 1\) here.")
        self.assertIn("`x = 1`", out)

    def test_escaped_dollar_is_ignored(self):
        # an escaped \$ should not start an inline math segment
        out = preprocess(r"Price is \$5 or \$10.")
        self.assertNotIn("`5 or ", out)


class TestCodeBlocksAreProtected(unittest.TestCase):
    def test_fenced_block_unchanged(self):
        src = "```python\nx = '$$not math$$'\n```"
        out = preprocess(src)
        self.assertIn("$$not math$$", out)

    def test_math_outside_fence_still_converts(self):
        src = "```\nraw\n```\n\n$$x^2$$"
        out = preprocess(src)
        self.assertIn("x²", out)
        self.assertIn("raw", out)


class TestRoundTrip(unittest.TestCase):
    def test_full_example(self):
        src = (
            "# Physik\n\n"
            r"$$\lambda_{\text{peak}} = \frac{b}{T}$$" "\n\n"
            "Inline: $T^4$.\n"
        )
        out = preprocess(src)
        self.assertIn("λₚₑₐₖ = b/T", out)
        self.assertIn("`T⁴`", out)


if __name__ == "__main__":
    unittest.main()

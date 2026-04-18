"""Unit tests for the LaTeX-to-Unicode conversion."""
import unittest

from conftest import load_innomd

innomd = load_innomd()
convert_math = innomd.convert_math


class TestGreekLetters(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(convert_math(r"\lambda"), "λ")
        self.assertEqual(convert_math(r"\varepsilon"), "ε")
        self.assertEqual(convert_math(r"\sigma"), "σ")
        self.assertEqual(convert_math(r"\pi"), "π")
        self.assertEqual(convert_math(r"\mu"), "μ")

    def test_uppercase(self):
        self.assertEqual(convert_math(r"\Sigma"), "Σ")
        self.assertEqual(convert_math(r"\Omega"), "Ω")
        self.assertEqual(convert_math(r"\Delta"), "Δ")

    def test_no_partial_match(self):
        # \lambda must not match \lambdaX
        self.assertEqual(convert_math(r"\lambdax"), r"\lambdax")


class TestOperators(unittest.TestCase):
    def test_common(self):
        self.assertEqual(convert_math(r"a \cdot b"), "a · b")
        self.assertEqual(convert_math(r"a \times b"), "a × b")
        self.assertEqual(convert_math(r"a \pm b"), "a ± b")
        self.assertEqual(convert_math(r"a \approx b"), "a ≈ b")
        self.assertEqual(convert_math(r"a \neq b"), "a ≠ b")
        self.assertEqual(convert_math(r"a \leq b"), "a ≤ b")

    def test_calculus(self):
        self.assertIn("∇", convert_math(r"\nabla f"))
        self.assertIn("∫", convert_math(r"\int f dx"))
        self.assertIn("∑", convert_math(r"\sum_i x_i"))
        self.assertIn("∞", convert_math(r"\infty"))
        self.assertIn("∂", convert_math(r"\partial"))


class TestSuperSubscripts(unittest.TestCase):
    def test_simple_superscript(self):
        self.assertEqual(convert_math(r"x^2"), "x²")
        self.assertEqual(convert_math(r"T^4"), "T⁴")
        self.assertEqual(convert_math(r"a^n"), "aⁿ")

    def test_braced_superscript(self):
        self.assertEqual(convert_math(r"10^{-3}"), "10⁻³")
        self.assertEqual(convert_math(r"x^{10}"), "x¹⁰")

    def test_simple_subscript(self):
        self.assertEqual(convert_math(r"x_0"), "x₀")
        self.assertEqual(convert_math(r"a_i"), "aᵢ")

    def test_braced_subscript_word(self):
        # lowercase word fits the subscript map
        self.assertEqual(convert_math(r"\lambda_{peak}"), "λₚₑₐₖ")

    def test_uppercase_subscript_fallback(self):
        # 'B' is not in the subscript map; single-char fallback keeps '_B'
        self.assertEqual(convert_math(r"k_B"), "k_B")

    def test_mixed_subscript_fallback(self):
        # multi-char unmapped falls back to _(…)
        result = convert_math(r"x_{AB}")
        self.assertEqual(result, "x_(AB)")


class TestFractions(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(convert_math(r"\frac{a}{b}"), "a/b")

    def test_complex_wraps_in_parens(self):
        # operands containing spaces or +/- get parenthesised for clarity
        self.assertEqual(convert_math(r"\frac{a+b}{c}"), "(a+b)/(c)")

    def test_nested(self):
        # nested \frac resolves outer after inner
        result = convert_math(r"\frac{\frac{1}{2}}{3}")
        self.assertIn("/", result)
        self.assertIn("1/2", result)


class TestRoots(unittest.TestCase):
    def test_sqrt(self):
        self.assertEqual(convert_math(r"\sqrt{x}"), "√(x)")

    def test_nth_root(self):
        self.assertEqual(convert_math(r"\sqrt[3]{x}"), "³√(x)")


class TestTextAndModifiers(unittest.TestCase):
    def test_text_strip(self):
        self.assertEqual(convert_math(r"\text{hello}"), "hello")

    def test_mathrm_strip(self):
        self.assertEqual(convert_math(r"\mathrm{m}"), "m")

    def test_vec(self):
        self.assertEqual(convert_math(r"\vec{E}"), "E⃗")

    def test_hat(self):
        self.assertEqual(convert_math(r"\hat{x}"), "x̂")


class TestComposite(unittest.TestCase):
    def test_wien_law(self):
        src = r"\lambda_{\text{peak}} = \frac{b}{T}"
        self.assertEqual(convert_math(src), "λₚₑₐₖ = b/T")

    def test_stefan_boltzmann(self):
        src = r"P = \varepsilon \cdot \sigma \cdot A \cdot T^4"
        self.assertEqual(convert_math(src), "P = ε · σ · A · T⁴")

    def test_spaces_and_units(self):
        src = r"b = 2{,}898 \times 10^{-3} \text{ m·K}"
        result = convert_math(src)
        self.assertIn("2,898", result)
        self.assertIn("× 10⁻³", result)
        self.assertIn("m·K", result)

    def test_mathbb(self):
        self.assertEqual(convert_math(r"\mathbb{R}"), "ℝ")
        self.assertEqual(convert_math(r"\mathbb{N}"), "ℕ")


if __name__ == "__main__":
    unittest.main()

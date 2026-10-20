import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host" / "plugins"))
import calculator as calc  # noqa: E402


def answer(text, degrees=False):
    found = calc.evaluate(text, degrees)
    return calc.format_number(found[0]) if found else None


class EvaluateTests(unittest.TestCase):
    def test_arithmetic(self):
        for text, want in [("2+2", "4"), ("2 + 3 * 4", "14"), ("(2+3)*4", "20"), ("10/4", "2.5"), ("7//2", "3"),
                           ("10 % 3", "1"), ("2^10", "1024"), ("2**3**2", "512"), ("-3 + 5", "2"), ("1.5*2", "3"),
                           ("6×7", "42"), ("84÷2", "42"), ("0.1+0.2", "0.3")]:
            self.assertEqual(answer(text), want, text)

    def test_functions_and_constants(self):
        self.assertEqual(answer("sqrt(16) * 3"), "12")
        self.assertEqual(answer("pi * 2"), "6.28318530718")
        self.assertEqual(answer("log(1000)"), "3")
        self.assertEqual(answer("ln(e)"), "1")
        self.assertEqual(answer("fact(5)"), "120")
        self.assertEqual(answer("round(2.567, 1)"), "2.6")
        self.assertEqual(answer("abs(-4) + 1"), "5")

    def test_angles(self):
        self.assertEqual(answer("sin(30)", degrees=True), "0.5")
        self.assertEqual(answer("asin(1)", degrees=True), "90")
        self.assertEqual(answer("cos(0)"), "1")

    def test_percent_forms(self):
        self.assertEqual(answer("20% of 50"), "10")
        self.assertEqual(answer("100 + 10%"), "110")
        self.assertEqual(answer("200 - 25%"), "150")
        self.assertEqual(answer("50%*4"), "2")

    def test_big_results(self):
        self.assertEqual(answer("2**70"), "1.18059162072e+21")
        self.assertEqual(answer("10**15"), "1000000000000000")

    def test_things_that_are_not_math_stay_search_queries(self):
        for text in ["", "5", "-5", "pi", "e", "firefox", "7-zip", "gtk-3", "1password", "3d", "a+b", "2+", "(2+3",
                     "__import__('os')", "open('x')", "[1,2]", "2 if 1 else 3", "lambda: 1", "x" * 300]:
            self.assertIsNone(answer(text), text)

    def test_errors_become_no_answer(self):
        for text in ["1/0", "sqrt(-1)", "2**100000", "log(0)", "fact(-1)", "fact(2.5)", "fact(1000)", "9**9**9"]:
            self.assertIsNone(answer(text), text)


class FakeApi:
    def __init__(self, settings=None):
        self._settings = settings or {}
        self.copied = []

    def settings(self, _id):
        return self._settings

    def copy(self, text):
        self.copied.append(text)


class ProviderTests(unittest.TestCase):
    def test_answer_row_and_actions(self):
        api = FakeApi()
        provider = calc.Calculator(api)
        [row] = provider.answers("20% of 50")
        self.assertEqual((row["title"], row["subtitle"]), ("10", "20% of 50 ="))
        self.assertEqual(provider.answers("firefox"), [])
        candidate = dict(row)
        self.assertEqual(provider.perform(candidate, "copy", {})["hud"], "Copied 10")
        provider.perform(candidate, "copy-equation", {})
        self.assertEqual(api.copied, ["10", "20% of 50 = 10"])
        self.assertIsNone(provider.perform(candidate, "nope", {}))

    def test_angle_unit_setting(self):
        self.assertEqual(calc.Calculator(FakeApi({"angle_unit": "degrees"})).answers("sin(90)")[0]["title"], "1")
        self.assertEqual(calc.Calculator(FakeApi()).answers("sin(90)")[0]["title"], "0.893996663601")


if __name__ == "__main__":
    unittest.main()

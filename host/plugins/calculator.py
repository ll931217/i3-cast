"""Calculator: when the query is a math expression, the answer appears above the results.

    2+2          4              sqrt(16) * 3      12            2^10     1024
    20% of 50    10             100 + 10%         110           10 % 3   1  (modulo)
    sin(30)      0.5 with `angle_unit: degrees`

Enter copies the answer. Settings (config.yaml):  plugins: {calculator: {angle_unit: radians | degrees}}
A bare number or a word is never an answer, so searching for "7-zip" or "e" is unaffected.
The expression is parsed with `ast` and walked by hand. Nothing is ever passed to eval().
"""
import ast
import math
import operator
import re

MAX_QUERY = 200
MAX_EXPONENT = 1000
SIGNIFICANT_DIGITS = 12

BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}
FUNCTIONS = {
    "sqrt": math.sqrt, "cbrt": math.cbrt, "abs": abs, "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
    "round": round, "ln": math.log, "log": math.log10, "log2": math.log2, "fact": math.factorial,
}
TRIG = {"sin": math.sin, "cos": math.cos, "tan": math.tan}
INVERSE_TRIG = {"asin": math.asin, "acos": math.acos, "atan": math.atan}

NUMBER = r"\d+(?:\.\d+)?"
PERCENT_OF = re.compile(r"(%s)\s*%%\s*of\s*" % NUMBER)
ADD_PERCENT = re.compile(r"^(.+?)\s*([+-])\s*(%s)\s*%%\s*$" % NUMBER)
PERCENT = re.compile(r"(%s)\s*%%(?=\s*(?:$|[+\-*/)]))" % NUMBER)


class NotMath(Exception):
    pass


def normalize(text):
    """Rewrite user notation as Python: × ÷ ^ and the percent forms."""
    s = text.strip().lower().replace("×", "*").replace("÷", "/").replace("^", "**")
    s = ADD_PERCENT.sub(lambda m: "(%s)*(1%s%s/100)" % (m.group(1), m.group(2), m.group(3)), s)
    s = PERCENT_OF.sub(lambda m: "(%s/100)*" % m.group(1), s)
    return PERCENT.sub(lambda m: "(%s/100)" % m.group(1), s)


class Evaluator:
    def __init__(self, degrees):
        self.degrees = degrees
        self.is_math = False  # saw an operator or a function call

    def run(self, node):
        if isinstance(node, ast.Expression):
            return self.run(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name) and node.id in CONSTANTS:
            return CONSTANTS[node.id]
        if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
            return UNARY[type(node.op)](self.run(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            self.is_math = True
            left, right = self.run(node.left), self.run(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
                raise NotMath("exponent too large")
            return BINARY[type(node.op)](left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords and len(node.args) in (1, 2):
            self.is_math = True
            return self.call(node.func.id, [self.run(a) for a in node.args])
        raise NotMath(type(node).__name__)

    def call(self, name, args):
        if name in TRIG:
            return TRIG[name](math.radians(args[0]) if self.degrees else args[0])
        if name in INVERSE_TRIG:
            result = INVERSE_TRIG[name](args[0])
            return math.degrees(result) if self.degrees else result
        if name in FUNCTIONS and (len(args) == 1 or name in ("round", "ln")):
            if name == "fact" and not (float(args[0]).is_integer() and 0 <= args[0] <= 170):
                raise NotMath("factorial")
            return FUNCTIONS[name](*[int(args[0]) if name == "fact" else args[0]] + args[1:])
        raise NotMath("unknown function " + name)


def evaluate(text, degrees=False):
    """(value, expression) when text is a math expression, else None."""
    if not text or len(text) > MAX_QUERY:
        return None
    expression = normalize(text)
    try:
        tree = ast.parse(expression, mode="eval")
        evaluator = Evaluator(degrees)
        value = evaluator.run(tree)
    except (SyntaxError, NotMath, ArithmeticError, ValueError, TypeError, RecursionError, MemoryError):
        return None
    if not evaluator.is_math or isinstance(value, complex) or not math.isfinite(value):
        return None
    return value, text.strip()


def format_number(value):
    if isinstance(value, int) and abs(value) < 10 ** 18:
        return str(value)
    text = "%.*g" % (SIGNIFICANT_DIGITS, value)
    if "e" not in text and "." not in text:
        return text
    if float(text).is_integer() and abs(float(text)) < 1e15:
        return str(int(float(text)))
    return text


class Calculator:
    id = "calculator"

    def __init__(self, api):
        self.api = api

    def degrees(self):
        return str(self.api.settings(self.id).get("angle_unit", "radians")) == "degrees"

    def candidates(self):
        return []

    def answers(self, query):
        found = evaluate(query, self.degrees())
        if not found:
            return []
        value, expression = found
        answer = format_number(value)
        return [{
            "id": "answer", "title": answer, "subtitle": expression + " =", "type_label": "Calculator",
            "glyph": "", "keywords": [], "data": {"answer": answer, "expression": expression},
        }]

    def actions_for(self, candidate):
        return [
            {"id": "copy", "title": "Copy Answer", "icon": ""},
            {"id": "copy-equation", "title": "Copy Expression and Answer", "icon": ""},
        ]

    def perform(self, candidate, action, ctx):
        data = candidate["data"]
        if action == "copy":
            text = data["answer"]
        elif action == "copy-equation":
            text = "%s = %s" % (data["expression"], data["answer"])
        else:
            return None
        self.api.copy(text)
        return {"close": True, "hud": "Copied " + text}


def register(api):
    api.add_provider(Calculator(api))

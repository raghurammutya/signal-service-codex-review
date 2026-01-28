"""
Formula Engine for custom calculations
Safely evaluates mathematical expressions with access to market data and indicators
"""
import ast
import math
import operator
from datetime import datetime
from typing import Any

import pandas as pd

from app.utils.logging_utils import log_exception, log_info


class FormulaEngine:
    """
    Safe formula evaluation engine for custom calculations
    Supports mathematical operations on market data and technical indicators
    """

    # Allowed operators
    ALLOWED_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        ast.Lt: operator.lt,
        ast.Gt: operator.gt,
        ast.LtE: operator.le,
        ast.GtE: operator.ge,
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.And: operator.and_,
        ast.Or: operator.or_,
        ast.Not: operator.not_,
    }

    # Allowed functions
    ALLOWED_FUNCTIONS = {
        # Math functions
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
        'len': len,

        # Math module functions
        'sqrt': math.sqrt,
        'pow': math.pow,
        'log': math.log,
        'log10': math.log10,
        'exp': math.exp,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'asin': math.asin,
        'acos': math.acos,
        'atan': math.atan,
        'ceil': math.ceil,
        'floor': math.floor,

        # Pandas functions (for series operations)
        'rolling': lambda s, window: s.rolling(window) if isinstance(s, pd.Series) else None,
        'shift': lambda s, periods: s.shift(periods) if isinstance(s, pd.Series) else None,
        'diff': lambda s: s.diff() if isinstance(s, pd.Series) else None,
        'pct_change': lambda s: s.pct_change() if isinstance(s, pd.Series) else None,
        'cumsum': lambda s: s.cumsum() if isinstance(s, pd.Series) else None,
        'cumprod': lambda s: s.cumprod() if isinstance(s, pd.Series) else None,
        'mean': lambda s: s.mean() if isinstance(s, pd.Series) else None,
        'std': lambda s: s.std() if isinstance(s, pd.Series) else None,
        'var': lambda s: s.var() if isinstance(s, pd.Series) else None,
        'median': lambda s: s.median() if isinstance(s, pd.Series) else None,
        'quantile': lambda s, q: s.quantile(q) if isinstance(s, pd.Series) else None,
    }

    # Constants
    ALLOWED_CONSTANTS = {
        'pi': math.pi,
        'e': math.e,
        'true': True,
        'false': False,
        'none': None,
    }

    def __init__(self):
        self._compiled_formulas: dict[str, ast.AST] = {}
        self._formula_metadata: dict[str, dict[str, Any]] = {}

    def evaluate(
        self,
        formula: str,
        context: dict[str, Any],
        cache_key: str | None = None
    ) -> Any:
        """
        Safely evaluate a formula with given context

        Args:
            formula: Mathematical formula to evaluate
            context: Variables and data available to the formula
            cache_key: Optional key for caching compiled formula

        Returns:
            Result of formula evaluation
        """
        try:
            # Check cache
            if cache_key and cache_key in self._compiled_formulas:
                parsed = self._compiled_formulas[cache_key]
                log_info(f"Using cached formula: {cache_key}")
            else:
                # Parse and validate formula
                parsed = self._parse_formula(formula)
                if cache_key:
                    self._compiled_formulas[cache_key] = parsed

            # Create safe evaluation context
            safe_context = self._create_safe_context(context)

            # Evaluate
            result = self._eval_node(parsed, safe_context)

            # Handle pandas Series results
            if isinstance(result, pd.Series):
                # Return the last value for real-time calculations
                return result.iloc[-1] if not result.empty else None

            return result

        except Exception as e:
            log_exception(f"Error evaluating formula '{formula}': {str(e)}")
            raise ValueError(f"Formula evaluation failed: {str(e)}") from e

    def validate(self, formula: str) -> dict[str, Any]:
        """
        Validate a formula without evaluating it

        Args:
            formula: Formula to validate

        Returns:
            Validation result with variables and functions used
        """
        try:
            # Parse formula
            parsed = self._parse_formula(formula)

            # Extract variables and functions
            variables = set()
            functions = set()

            class Visitor(ast.NodeVisitor):
                def visit_Name(self, node):  # noqa: N802
                    variables.add(node.id)
                    self.generic_visit(node)

                def visit_Call(self, node):  # noqa: N802
                    if isinstance(node.func, ast.Name):
                        functions.add(node.func.id)
                    self.generic_visit(node)

            visitor = Visitor()
            visitor.visit(parsed)

            # Remove built-in constants from variables
            variables -= set(self.ALLOWED_CONSTANTS.keys())

            return {
                "valid": True,
                "variables": list(variables),
                "functions": list(functions),
                "formula": formula
            }

        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "formula": formula
            }

    def _parse_formula(self, formula: str) -> ast.AST:
        """Parse and validate formula syntax"""
        try:
            # Parse the formula
            parsed = ast.parse(formula, mode='eval')

            # Validate nodes
            self._validate_node(parsed.body)

            return parsed.body

        except SyntaxError as e:
            raise ValueError(f"Invalid formula syntax: {str(e)}") from e
        except Exception as e:
            raise ValueError(f"Formula parsing failed: {str(e)}") from e

    def _validate_node(self, node: ast.AST):
        """Recursively validate AST nodes for safety"""
        if isinstance(node, ast.BinOp):
            if type(node.op) not in self.ALLOWED_OPS:
                raise ValueError(f"Operator {type(node.op).__name__} not allowed")
            self._validate_node(node.left)
            self._validate_node(node.right)

        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in self.ALLOWED_OPS:
                raise ValueError(f"Operator {type(node.op).__name__} not allowed")
            self._validate_node(node.operand)

        elif isinstance(node, ast.Compare):
            for op in node.ops:
                if type(op) not in self.ALLOWED_OPS:
                    raise ValueError(f"Comparison {type(op).__name__} not allowed")
            for comparator in [node.left] + node.comparators:
                self._validate_node(comparator)

        elif isinstance(node, ast.BoolOp):
            if type(node.op) not in self.ALLOWED_OPS:
                raise ValueError(f"Boolean operator {type(node.op).__name__} not allowed")
            for value in node.values:
                self._validate_node(value)

        elif isinstance(node, ast.Call):
            # Only allow specific functions
            if isinstance(node.func, ast.Name):
                if node.func.id not in self.ALLOWED_FUNCTIONS:
                    raise ValueError(f"Function '{node.func.id}' not allowed")
            else:
                raise ValueError("Complex function calls not allowed")

            # Validate arguments
            for arg in node.args:
                self._validate_node(arg)
            for keyword in node.keywords:
                self._validate_node(keyword.value)

        elif isinstance(node, ast.IfExp):
            # Ternary operator: test if condition else else_value
            self._validate_node(node.test)
            self._validate_node(node.body)
            self._validate_node(node.orelse)

        elif isinstance(node, ast.Name):
            # Variable names are allowed
            pass

        elif isinstance(node, ast.Constant):
            # Constants are allowed
            pass

        elif isinstance(node, ast.Num):  # For Python < 3.8
            # Numbers are allowed
            pass

        elif isinstance(node, ast.Str):  # For Python < 3.8
            # Strings are allowed
            pass

        elif isinstance(node, ast.list):
            # Lists are allowed
            for elt in node.elts:
                self._validate_node(elt)

        elif isinstance(node, ast.tuple):
            # Tuples are allowed
            for elt in node.elts:
                self._validate_node(elt)

        elif isinstance(node, ast.Subscript):
            # Array/dict access is allowed
            self._validate_node(node.value)
            self._validate_node(node.slice)

        elif isinstance(node, ast.Index):  # For Python < 3.9
            # Index access
            self._validate_node(node.value)

        else:
            raise ValueError(f"AST node type {type(node).__name__} not allowed")

    def _create_safe_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Create a safe evaluation context"""
        safe_context = {}

        # Add allowed constants
        safe_context.update(self.ALLOWED_CONSTANTS)

        # Add allowed functions
        safe_context.update(self.ALLOWED_FUNCTIONS)

        # Add user context (market data, indicators, etc.)
        safe_context.update(context)

        # Add helper functions
        safe_context['iif'] = lambda cond, true_val, false_val: true_val if cond else false_val
        safe_context['between'] = lambda val, low, high: low <= val <= high
        safe_context['crossover'] = self._crossover
        safe_context['crossunder'] = self._crossunder

        return safe_context

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> Any:
        """Recursively evaluate AST nodes"""
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            return self.ALLOWED_OPS[type(node.op)](left, right)

        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            return self.ALLOWED_OPS[type(node.op)](operand)

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators, strict=False):
                right = self._eval_node(comparator, context)
                if not self.ALLOWED_OPS[type(op)](left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._eval_node(value, context) for value in node.values)
            # Or
            return any(self._eval_node(value, context) for value in node.values)

        if isinstance(node, ast.Call):
            func = context.get(node.func.id)
            if func is None:
                raise ValueError(f"Unknown function: {node.func.id}")

            args = [self._eval_node(arg, context) for arg in node.args]
            kwargs = {kw.arg: self._eval_node(kw.value, context) for kw in node.keywords}

            return func(*args, **kwargs)

        if isinstance(node, ast.IfExp):
            test = self._eval_node(node.test, context)
            if test:
                return self._eval_node(node.body, context)
            return self._eval_node(node.orelse, context)

        if isinstance(node, ast.Name):
            if node.id not in context:
                raise ValueError(f"Unknown variable: {node.id}")
            return context[node.id]

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Num | ast.Str):  # For Python < 3.8
            return node.n if isinstance(node, ast.Num) else node.s

        if isinstance(node, ast.list):
            return [self._eval_node(elt, context) for elt in node.elts]

        if isinstance(node, ast.tuple):
            return tuple(self._eval_node(elt, context) for elt in node.elts)

        if isinstance(node, ast.Subscript):
            value = self._eval_node(node.value, context)
            if isinstance(node.slice, ast.Index):  # Python < 3.9
                index = self._eval_node(node.slice.value, context)
            else:
                index = self._eval_node(node.slice, context)
            return value[index]

        raise ValueError(f"Unsupported node type: {type(node).__name__}")

    def _crossover(self, series1: pd.Series, series2: pd.Series) -> bool:
        """Check if series1 crosses over series2"""
        if not isinstance(series1, pd.Series) or not isinstance(series2, pd.Series):
            return False

        if len(series1) < 2 or len(series2) < 2:
            return False

        return (series1.iloc[-2] <= series2.iloc[-2] and
                series1.iloc[-1] > series2.iloc[-1])

    def _crossunder(self, series1: pd.Series, series2: pd.Series) -> bool:
        """Check if series1 crosses under series2"""
        if not isinstance(series1, pd.Series) or not isinstance(series2, pd.Series):
            return False

        if len(series1) < 2 or len(series2) < 2:
            return False

        return (series1.iloc[-2] >= series2.iloc[-2] and
                series1.iloc[-1] < series2.iloc[-1])

    def create_formula_template(
        self,
        name: str,
        formula: str,
        description: str,
        parameters: dict[str, Any],
        examples: list[str]
    ) -> dict[str, Any]:
        """
        Create a reusable formula template

        Args:
            name: Template name
            formula: Formula expression
            description: Human-readable description
            parameters: Required parameters
            examples: Usage examples

        Returns:
            Template metadata
        """
        # Validate formula
        validation = self.validate(formula)
        if not validation["valid"]:
            raise ValueError(f"Invalid formula: {validation['error']}")

        template = {
            "name": name,
            "formula": formula,
            "description": description,
            "parameters": parameters,
            "variables": validation["variables"],
            "functions": validation["functions"],
            "examples": examples,
            "created_at": datetime.utcnow()
        }

        self._formula_metadata[name] = template

        return template

    def get_builtin_formulas(self) -> list[dict[str, Any]]:
        """Get list of built-in formula templates"""
        return [
            {
                "name": "price_to_sma",
                "formula": "(close - sma) / sma * 100",
                "description": "Percentage distance from Simple Moving Average",
                "parameters": {"sma": "Simple Moving Average series"},
                "examples": ["(close - sma20) / sma20 * 100"]
            },
            {
                "name": "bollinger_position",
                "formula": "(close - bb_lower) / (bb_upper - bb_lower)",
                "description": "Position within Bollinger Bands (0-1)",
                "parameters": {
                    "bb_upper": "Upper Bollinger Band",
                    "bb_lower": "Lower Bollinger Band"
                },
                "examples": ["(close - bb_lower) / (bb_upper - bb_lower)"]
            },
            {
                "name": "momentum_score",
                "formula": "(rsi / 100) * 0.3 + (close > sma20) * 0.4 + (volume > vol_avg) * 0.3",
                "description": "Composite momentum score (0-1)",
                "parameters": {
                    "rsi": "RSI value",
                    "sma20": "20-period SMA",
                    "vol_avg": "Average volume"
                },
                "examples": ["(rsi / 100) * 0.3 + (close > sma20) * 0.4 + (volume > vol_avg) * 0.3"]
            },
            {
                "name": "volatility_adjusted_return",
                "formula": "returns / volatility * sqrt(252)",
                "description": "Sharpe-like ratio for returns",
                "parameters": {
                    "returns": "Return series",
                    "volatility": "Volatility value"
                },
                "examples": ["pct_change(close) / std(pct_change(close)) * sqrt(252)"]
            },
            {
                "name": "mean_reversion_signal",
                "formula": "iif(abs(close - mean) > 2 * std, sign(mean - close), 0)",
                "description": "Mean reversion signal when price is 2 std devs away",
                "parameters": {
                    "mean": "Mean price (e.g., SMA)",
                    "std": "Standard deviation"
                },
                "examples": ["iif(abs(close - sma50) > 2 * std(close), sign(sma50 - close), 0)"]
            }
        ]


# Global formula engine instance
formula_engine = FormulaEngine()

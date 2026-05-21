"""Run-level check evaluation for Phase 1."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from datamapx.config import CheckConfig
from datamapx.transform.errors import MappingError

BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

COMPARE_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}


@dataclass(frozen=True)
class CheckResult:
    """Result of one run-level check."""

    name: str
    rule: str
    passed: bool
    evaluated_value: Any
    message: str | None = None


def evaluate_checks(checks: list[CheckConfig], context: dict[str, Any]) -> list[CheckResult]:
    """Evaluate configured checks against run-level summary values."""

    results: list[CheckResult] = []
    for check in checks:
        evaluated_value = _evaluate_rule(check.rule, context)
        passed = bool(evaluated_value)
        results.append(
            CheckResult(
                name=check.name,
                rule=check.rule,
                passed=passed,
                evaluated_value=evaluated_value,
                message=None if passed else f"check failed: {check.rule}",
            )
        )
    return results


def _evaluate_rule(rule: str, context: dict[str, Any]) -> Any:
    if not isinstance(rule, str):
        raise MappingError("checks: rule must be a string")

    try:
        tree = ast.parse(rule, mode="eval")
    except SyntaxError as exc:
        raise MappingError(f"checks: invalid syntax: {rule}") from exc

    _validate_ast(tree, context)
    return _eval_node(tree.body, context)


def _validate_ast(tree: ast.Expression, context: dict[str, Any]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load, ast.Constant, ast.Name)):
            continue
        if isinstance(node, ast.BinOp):
            if type(node.op) not in BIN_OPS:
                raise MappingError("checks: unsupported operator")
            continue
        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in UNARY_OPS:
                raise MappingError("checks: unsupported operator")
            continue
        if isinstance(node, ast.BoolOp):
            if not isinstance(node.op, (ast.And, ast.Or)):
                raise MappingError("checks: unsupported operator")
            continue
        if isinstance(node, ast.Compare):
            if any(type(op) not in COMPARE_OPS for op in node.ops):
                raise MappingError("checks: unsupported comparison operator")
            continue
        if isinstance(node, ast.Call):
            _validate_call(node)
            continue
        if isinstance(node, ast.Attribute):
            raise MappingError(
                "checks: field references are not supported yet; use summary variables only"
            )
        if isinstance(node, tuple(BIN_OPS) + tuple(UNARY_OPS) + tuple(COMPARE_OPS)):
            continue
        raise MappingError(f"checks: unsupported syntax: {type(node).__name__}")

    for name in context:
        if not name.isidentifier():
            raise MappingError(f"checks: invalid context variable name: {name}")


def _validate_call(node: ast.Call) -> None:
    if not isinstance(node.func, ast.Name):
        raise MappingError("checks: unsupported function call")
    if node.keywords:
        raise MappingError("checks: keyword arguments are not supported")


def _eval_node(node: ast.AST, context: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)) or node.value is None:
            return node.value
        raise MappingError("checks: unsupported literal")
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise MappingError(f"checks: unknown variable: {node.id}")
        return context[node.id]
    if isinstance(node, ast.BinOp):
        op = BIN_OPS.get(type(node.op))
        if op is None:
            raise MappingError("checks: unsupported operator")
        return op(_eval_node(node.left, context), _eval_node(node.right, context))
    if isinstance(node, ast.UnaryOp):
        op = UNARY_OPS.get(type(node.op))
        if op is None:
            raise MappingError("checks: unsupported operator")
        return op(_eval_node(node.operand, context))
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(value, context) for value in node.values]
        if isinstance(node.op, ast.And):
            result = values[0]
            for value in values[1:]:
                result = result and value
            return result
        if isinstance(node.op, ast.Or):
            result = values[0]
            for value in values[1:]:
                result = result or value
            return result
        raise MappingError("checks: unsupported operator")
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, context)
        for operator_node, comparator in zip(node.ops, node.comparators, strict=True):
            comparator_value = _eval_node(comparator, context)
            compare = COMPARE_OPS.get(type(operator_node))
            if compare is None:
                raise MappingError("checks: unsupported comparison operator")
            if not compare(left, comparator_value):
                return False
            left = comparator_value
        return True
    if isinstance(node, ast.Call):
        raise MappingError("checks: function calls are not supported")
    raise MappingError(f"checks: unsupported syntax: {type(node).__name__}")

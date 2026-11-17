"""Restricted Python inspection via AST allow-list.

This module only *inspects* source. It never executes it. Syntax checking and
execution are separate functions (see review.py) and execution is opt-in.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .config import canonical_route, ROUTE_UNKNOWN
from .models import PythonSnippet
from .programs import AND, NOT, OR, Guard, cmp, from_model
from .models import GuardModel, ComparisonModel

ALLOWED_COMPARE = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.GtE: ">=",
    ast.Gt: ">",
    ast.LtE: "<=",
    ast.Lt: "<",
    ast.Is: "==",
    ast.IsNot: "!=",
}


@dataclass
class ParsedSnippet:
    snippet: PythonSnippet
    program: object | None = None
    syntax_ok: bool = True
    unsupported: list[str] = field(default_factory=list)
    approval_claims: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.program is not None and self.error is None


class SubsetError(ValueError):
    pass


def _const(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    raise SubsetError(f"only literal constants are allowed, got {type(node).__name__}")


def condition_from_ast(node: ast.AST, feature_units: dict[str, str]) -> Guard:
    if isinstance(node, ast.BoolOp):
        parts = [condition_from_ast(v, feature_units) for v in node.values]
        return AND(*parts) if isinstance(node.op, ast.And) else OR(*parts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return NOT(condition_from_ast(node.operand, feature_units))
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        op = ALLOWED_COMPARE.get(type(node.ops[0]))
        if op is None:
            raise SubsetError(f"comparison {type(node.ops[0]).__name__} is not supported")
        left, right = node.left, node.comparators[0]
        if isinstance(left, ast.Name) and not isinstance(right, ast.Name):
            feature, value_node = left.id, right
        elif isinstance(right, ast.Name) and not isinstance(left, ast.Name):
            feature, value_node = right.id, left
            op = {"==": "==", "!=": "!=", ">=": "<=", ">": "<",
                  "<=": ">=", "<": ">"}.get(op, op)
        else:
            raise SubsetError("comparison must have one named feature and one literal")
        value = _const(value_node)
        if isinstance(value, ast.AST):
            raise SubsetError("unsupported comparison operand")
        gm = GuardModel(
            kind="cmp",
            comparison=ComparisonModel(feature=feature, op=op, value=value, unit=feature_units.get(feature)),
        )
        guard, warnings = from_model(gm, feature_units)
        return guard
    if isinstance(node, ast.Name):
        return cmp(node.id, "==", True)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        from .programs import TRUE, FALSE
        return TRUE if node.value else FALSE
    raise SubsetError(f"unsupported condition node {type(node).__name__}")


def route_from_ast(node: ast.AST) -> str:
    value = _const(node)
    if not isinstance(value, str):
        raise SubsetError("return value must be a string route constant")
    route = canonical_route(value)
    if route == ROUTE_UNKNOWN:
        raise SubsetError(f"unknown route constant '{value}'")
    return route


def inspect_snippet(snippet: PythonSnippet, feature_units: dict[str, str] | None = None
                    ) -> ParsedSnippet:
    result = ParsedSnippet(snippet=snippet)
    from .patterns import find_approval_claims
    result.approval_claims = find_approval_claims(snippet.code)
    try:
        tree = ast.parse(snippet.code)
    except SyntaxError as exc:
        result.syntax_ok = False
        result.error = f"syntax error: {exc.msg} at line {exc.lineno}"
        return result

    func = None
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.For, ast.While, ast.ClassDef)):
            result.unsupported.append(f"{type(node).__name__} is outside the supported subset")
        if isinstance(node, ast.FunctionDef) and node.name == snippet.function:
            func = node
    if func is None and snippet.function in ("", "*"):
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        func = funcs[0] if funcs else None
    if func is None:
        result.error = f"function '{snippet.function}' not found"
        return result

    rules: list[tuple[Guard, str]] = []
    try:
        rules = _walk_block(func.body, __import__("verdict.programs", fromlist=["TRUE"]).TRUE,
                           feature_units or {}, result.unsupported)
        from .programs import DecisionProgram, Rule
        frozen = tuple(
            Rule(g, r, f"code:{snippet.path}:{snippet.function}:rule{i}", snippet.source_ref)
            for i, (g, r) in enumerate(rules)
        )
        result.program = DecisionProgram(
            origin=f"code:{snippet.path}", version=snippet.version,
            rules=frozen, default_route=ROUTE_UNKNOWN,
        )
    except SubsetError as exc:
        result.error = str(exc)
    return result


def _walk_block(stmts: list[ast.stmt], reach: Guard,
                feature_units: dict[str, str], unsupported: list[str]) -> list[tuple[Guard, str]]:
    """Compile a statement block into (guard, route) rules with path guards.

    Handles nested if/elif/else and fall-through. A return closes the current
    path; an if without else narrows `reach` with the negated condition.
    """
    from .programs import FALSE, AND, NOT
    out: list[tuple[Guard, str]] = []
    for stmt in stmts:
        if reach.kind == "false":
            break
        if isinstance(stmt, ast.If):
            test = condition_from_ast(stmt.test, feature_units)
            out.extend(_walk_block(stmt.body, AND(reach, test), feature_units, unsupported))
            if stmt.orelse:
                out.extend(_walk_block(stmt.orelse, AND(reach, NOT(test)),
                                       feature_units, unsupported))
                reach = FALSE
            else:
                reach = AND(reach, NOT(test))
        elif isinstance(stmt, ast.Return):
            out.append((reach, route_from_ast(stmt.value)))
            reach = FALSE
        else:
            unsupported.append(f"{type(stmt).__name__} statement is outside the supported subset")
    return out


def _rule_nodes(stmts: list[ast.stmt]) -> list[ast.stmt]:
    """Collect Return nodes in source order for evidence locations."""
    nodes: list[ast.stmt] = []

    def visit(items: list[ast.stmt]) -> None:
        for stmt in items:
            if isinstance(stmt, ast.Return):
                nodes.append(stmt)
            elif isinstance(stmt, ast.If):
                visit(stmt.body)
                visit(stmt.orelse)

    visit(stmts)
    return nodes


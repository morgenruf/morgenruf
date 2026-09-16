"""Prove a file move changed nothing except import lines.

Parses both versions, removes every Import and ImportFrom node at any nesting
level, and compares the resulting syntax trees. Used to gate the package split,
where the largest moved files have coverage too low to rely on tests alone.

CLI:
    python tools/check_mechanical_move.py <git_rev> <old_path> <new_path>

Exit code 0 means equivalent, 1 means a difference was found.
"""

from __future__ import annotations

import ast
import subprocess
import sys


class _StripImports(ast.NodeTransformer):
    def visit_Import(self, node: ast.Import):  # noqa: N802
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
        return None


def _normalise_module(source: str) -> str:
    tree = _StripImports().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False)


def modules_equivalent(old_source: str, new_source: str) -> bool:
    """True when the two sources differ only in import statements."""
    return _normalise_module(old_source) == _normalise_module(new_source)


def _function_dump(source: str, name: str) -> str | None:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            stripped = _StripImports().visit(node)
            ast.fix_missing_locations(stripped)
            return ast.dump(stripped, include_attributes=False)
    return None


def changed_functions(old_source: str, new_source: str, names: list[str]) -> list[str]:
    """Names whose bodies differ between the two sources.

    A function missing from either side counts as changed. Used when functions
    are extracted from a large module into a new one, where a whole-file
    comparison does not apply.
    """
    return [n for n in names if _function_dump(old_source, n) != _function_dump(new_source, n)]


class MissingRevision(Exception):
    """The requested path does not exist at the requested git revision."""


def _read_git(rev: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MissingRevision(f"{rev}:{path} not found ({result.stderr.strip()})")
    return result.stdout


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    rev, old_path, new_path = argv[1], argv[2], argv[3]
    try:
        old_source = _read_git(rev, old_path)
    except MissingRevision as exc:
        print(f"CANNOT COMPARE: {exc}", file=sys.stderr)
        return 3
    with open(new_path) as fh:
        new_source = fh.read()
    if modules_equivalent(old_source, new_source):
        print(f"OK mechanical: {old_path} -> {new_path}")
        return 0
    print(f"DIFFERS beyond imports: {old_path} -> {new_path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

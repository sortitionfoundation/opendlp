"""ABOUTME: Fails the build when a function handed a UnitOfWork opens its own context
ABOUTME: Only entrypoints - the code that builds the UnitOfWork - may open `with uow:`"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

#: The convention: only entrypoints open `with uow:`. Everything handed a
#: UnitOfWork assumes an open context. See docs/architecture.md.
DEFAULT_ROOT = pathlib.Path(__file__).resolve().parent.parent / "src" / "opendlp"

# Known blind spots, both of which under-report rather than over-report:
#  - only a context expression spelled exactly `uow` is recognised, so a
#    differently named UnitOfWork parameter is missed;
#  - a function that hands its `uow` to a callee that opens a context is not an
#    offender here, even though the nesting is the same problem.


def _takes_uow(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = func.args
    return "uow" in [arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)]


def _opens_own_context(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.With | ast.AsyncWith)
        and any(isinstance(item.context_expr, ast.Name) and item.context_expr.id == "uow" for item in node.items)
        for node in ast.walk(func)
    )


def find_self_managing(root: pathlib.Path) -> set[str]:
    """Return `<path>::<function>` for every function under root that opens its own context."""
    offenders = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and _takes_uow(node)
                and _opens_own_context(node)
            ):
                offenders.add(f"{path.relative_to(root).as_posix()}::{node.name}")
    return offenders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(DEFAULT_ROOT), help="directory to scan")
    args = parser.parse_args(argv)

    offenders = sorted(find_self_managing(pathlib.Path(args.root)))
    for name in offenders:
        print(f"{name}: takes a UnitOfWork and opens its own `with uow:`. Let the caller manage the context.")

    if offenders:
        print(f"\n{len(offenders)} function(s) open a context they were handed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

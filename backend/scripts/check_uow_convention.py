"""ABOUTME: Fails the build when a service-layer function opens its own UnitOfWork context
ABOUTME: Known offenders are listed in an allowlist that shrinks as they are migrated"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

#: The convention: only entrypoints open `with uow:`. Everything below the
#: entrypoint assumes an open context. See docs/agent/clean-uow-usage/plan.md.
DEFAULT_ROOT = pathlib.Path(__file__).resolve().parent.parent / "src" / "opendlp" / "service_layer"
DEFAULT_ALLOWLIST = (
    pathlib.Path(__file__).resolve().parent.parent / "docs" / "agent" / "clean-uow-usage" / "known_self_managing.txt"
)

#: How many offenders the allowlist was seeded with. The list may only shrink.
SEEDED_COUNT = 130

# Known blind spots, both of which under-report rather than over-report:
#  - only a context expression spelled exactly `uow` is recognised, so a
#    differently named UnitOfWork parameter is missed;
#  - a function that hands its `uow` to a self-managing callee is not an
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


def load_allowlist(path: pathlib.Path) -> set[str]:
    if not path.exists():
        return set()
    lines = (line.strip() for line in path.read_text().splitlines())
    return {line for line in lines if line and not line.startswith("#")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(DEFAULT_ROOT), help="directory to scan")
    parser.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST), help="file of known offenders")
    args = parser.parse_args(argv)

    allowlist_path = pathlib.Path(args.allowlist)
    offenders = find_self_managing(pathlib.Path(args.root))
    allowed = load_allowlist(allowlist_path)

    added = sorted(offenders - allowed)
    stale = sorted(allowed - offenders)

    for name in added:
        print(f"{name}: opens its own `with uow:`. Let the caller manage the context.")
    for name in stale:
        print(f"{name}: no longer opens its own context - remove it from {allowlist_path.name}.")

    if added or stale:
        print(f"\n{len(offenders)} self-managing function(s) remain; {len(allowed)} were expected.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

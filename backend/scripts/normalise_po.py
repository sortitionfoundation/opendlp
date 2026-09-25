"""ABOUTME: Rewrites gettext catalogues through Babel's writer so every tool's output shares one format
ABOUTME: Also clears fuzzy flags on request, which is how a reviewed translation is accepted"""

from __future__ import annotations

import argparse
import pathlib
import sys

from babel.messages.pofile import read_po, write_po

# Babel wraps at 76 columns and gettext's tools (msgattrib, msgcat, ...) at 79, and
# the two also break lines differently, so whichever wrote a catalogue last decides
# how the whole file is wrapped. `translate-regen` writes through Babel and cannot
# be replaced, so Babel's format is the canonical one and everything else is
# normalised to it before commit.


def normalise(path: pathlib.Path, accept_fuzzy: bool = False) -> bool:
    """Rewrite `path` in Babel's format; return whether its bytes changed.

    With `accept_fuzzy`, every fuzzy flag is cleared first, so a translation a
    reviewer has approved gets compiled into the .mo rather than skipped.
    """
    original = path.read_bytes()
    with path.open("rb") as handle:
        catalog = read_po(handle)
    if accept_fuzzy:
        for message in catalog:
            message.flags.discard("fuzzy")
    # The same flags translate-regen passes to pybabel update: obsolete entries
    # are dropped rather than kept as `#~` lines, and no `#|` previous-msgid lines.
    with path.open("wb") as handle:
        write_po(handle, catalog, ignore_obsolete=True, include_previous=False)
    # write_po ends with a blank line after the last entry; one newline is enough.
    normalised = path.read_bytes().rstrip(b"\n") + b"\n"
    path.write_bytes(normalised)
    return normalised != original


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalise gettext catalogues to Babel's format.")
    parser.add_argument("paths", nargs="+", type=pathlib.Path, help=".po or .pot files to rewrite")
    parser.add_argument("--accept-fuzzy", action="store_true", help="clear every fuzzy flag before writing")
    parser.add_argument(
        "--fail-if-changed",
        action="store_true",
        help="exit 1 when a file was rewritten, so a pre-commit hook can ask for it to be re-staged",
    )
    args = parser.parse_args(argv)

    changed = [path for path in args.paths if normalise(path, accept_fuzzy=args.accept_fuzzy)]
    for path in changed:
        print(f"normalised {path}")
    return 1 if changed and args.fail_if_changed else 0


if __name__ == "__main__":
    sys.exit(main())

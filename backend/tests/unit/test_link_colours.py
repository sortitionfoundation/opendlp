"""ABOUTME: Pins the link colour: both link tokens are link blue, the design's info-600
ABOUTME: and no template colours a link with --color-primary-action, the brand crimson"""

import re
from pathlib import Path

from opendlp import config

SEMANTIC_TOKENS = config.get_static_path() / "backoffice" / "tokens" / "semantic.css"

DEFINITION_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
# An <a> start tag, attributes and all, even when they run over several lines.
ANCHOR_RE = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
# A text colour of --color-primary-action; a border or background in it is not a link colour.
PRIMARY_ACTION_COLOUR_RE = re.compile(r"(?<![-\w])color\s*:\s*var\(\s*--color-primary-action\s*\)")

# The only links still coloured with --color-primary-action, and why.
PRIMARY_ACTION_LINKS = {
    # The error summary's links to the fields are red, like the errors they list.
    "backoffice/assembly_form.html": 1,
    # The page header's back arrow is an icon control, not a text link.
    "backoffice/components/page_header.html": 1,
}


def _definitions() -> dict[str, str]:
    return {name: value.strip() for name, value in DEFINITION_RE.findall(SEMANTIC_TOKENS.read_text())}


def _primary_action_links(root: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    for template in sorted(root.rglob("*.html")):
        count = sum(bool(PRIMARY_ACTION_COLOUR_RE.search(tag)) for tag in ANCHOR_RE.findall(template.read_text()))
        if count:
            found[str(template.relative_to(root))] = count
    return found


def test_link_tokens_are_link_blue() -> None:
    definitions = _definitions()
    assert definitions["--color-links"] == "var(--color-info-600)"
    assert definitions["--color-link-text"] == "var(--color-info-600)"
    assert definitions["--color-info-600"].upper() == "#2B5FA6"


def test_scan_finds_a_link_coloured_on_a_later_line(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text(
        '<a href="/x"\n   class="underline"\n   style="color: var(--color-primary-action)">x</a>'
        '<span style="color: var(--color-primary-action)">*</span>'
        '<a href="/y" style="color: var(--color-links)">y</a>'
        '<a href="/z" style="border-color: var(--color-primary-action)">z</a>'
    )
    assert _primary_action_links(tmp_path) == {"page.html": 1}


def test_no_link_is_coloured_with_the_primary_action_colour() -> None:
    """A link coloured with --color-primary-action stays crimson whatever --color-links says."""
    found = _primary_action_links(config.get_templates_path())
    assert found == PRIMARY_ACTION_LINKS, (
        "Links are link blue: colour them with var(--color-links), not var(--color-primary-action). "
        "If a link really has to be crimson, add it to PRIMARY_ACTION_LINKS with the reason. "
        f"Templates with an <a> coloured --color-primary-action: {found}"
    )

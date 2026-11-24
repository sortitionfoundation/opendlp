"""ABOUTME: Pins the error colours to the design's error reds, kept apart from the brand crimson, and fails
ABOUTME: if a template draws an error in --color-primary-action or the showcase prints a stale status colour"""

import re
from pathlib import Path

from opendlp import config

TOKENS = config.get_static_path() / "backoffice" / "tokens"
SEMANTIC_SHOWCASE = config.get_templates_path() / "backoffice" / "showcase" / "semantic_tokens.html"

DEFINITION_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
# A swatch on the showcase's Foundations tab: the token's name, then its value printed as text.
SWATCH_LABEL_RE = re.compile(
    r'<p class="text-code">\s*(--[a-z0-9-]+)\s*</p>\s*<p class="text-caption[^"]*">\s*(#[0-9A-Fa-f]{6})\s*</p>'
)
# An element coloured --color-primary-action whose content is an error: {{ error }}, {{ row_error }} and the like.
# A start tag can hold Jinja ({% if %} ... %}), so the tag runs to the last ">" before the expression, not the first.
ERROR_TEXT_RE = re.compile(
    r"<[a-z]+\b[^<]*?--color-primary-action[^<]*?>\s*\{\{\s*[\w.]*error[\w.]*\s*(?:\|[^}]*)?\}\}",
    re.IGNORECASE,
)
# A style that switches to --color-primary-action when something is in error: {% if has_error %}var(--color-primary-action)
ERROR_BRANCH_RE = re.compile(r"\{%-?\s*if\s+[^%]*error[^%]*-?%\}\s*var\(\s*--color-primary-action\s*\)", re.IGNORECASE)


def _definitions(token_file: str) -> dict[str, str]:
    return {name: value.strip() for name, value in DEFINITION_RE.findall((TOKENS / token_file).read_text())}


def _errors_in_primary_action(root: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    for template in sorted(root.rglob("*.html")):
        text = template.read_text()
        count = len(ERROR_TEXT_RE.findall(text)) + len(ERROR_BRANCH_RE.findall(text))
        if count:
            found[str(template.relative_to(root))] = count
    return found


def test_the_error_tokens_are_the_designs_error_reds() -> None:
    """The Colors section of the OpenDLP UI Figma file (node 1275:8124)."""
    definitions = _definitions("semantic.css")
    assert definitions["--color-error-100"].upper() == "#FCEBE7"
    assert definitions["--color-error-400"].upper() == "#D6361A"
    assert definitions["--color-error-600"].upper() == "#B42318"


def test_the_error_aliases_follow_the_error_scale() -> None:
    definitions = _definitions("semantic.css")
    assert definitions["--color-error-background"] == "var(--color-error-100)"
    assert definitions["--color-error-border"] == "var(--color-error-400)"
    assert definitions["--color-error-text"] == "var(--color-error-600)"


def test_no_error_red_is_a_brand_colour() -> None:
    """An error drawn in a brand colour looks like a primary action or a brand accent."""
    brand = {
        value.upper() for name, value in _definitions("primitive.css").items() if name.startswith("--color-brand-")
    }
    errors = {
        name: value.upper()
        for name, value in _definitions("semantic.css").items()
        if re.fullmatch(r"--color-error-\d+", name)
    }
    assert brand
    assert len(errors) == 3
    assert not set(errors.values()) & brand, f"Error tokens with a brand value: {errors}"


def test_the_showcase_prints_the_status_colours_values() -> None:
    """The Foundations tab prints each status colour's hex as text, which does not follow the token by itself."""
    definitions = _definitions("semantic.css")
    labels = SWATCH_LABEL_RE.findall(SEMANTIC_SHOWCASE.read_text())
    assert len(labels) == 12  # success, warning, error and info, each at 100, 400 and 600
    stale = {name: printed for name, printed in labels if definitions[name].upper() != printed.upper()}
    assert not stale, f"semantic_tokens.html prints a value its token no longer has: {stale}"


def test_scan_finds_an_error_drawn_in_the_primary_action_colour(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text(
        '<p id="x-error"\n   class="text-body-sm"\n   style="color: var(--color-primary-action);">{{ error }}</p>'
        '<p style="color: var(--color-primary-action);">{{ row_error }}</p>'
        '<input style="border: 1px solid {% if has_error %}var(--color-primary-action){% else %}var(--x){% endif %};">'
        '<p style="color: var(--color-error-text);">{{ error }}</p>'
        '<span style="color: var(--color-primary-action);">*</span>'
        '<p style="color: var(--color-primary-action);">{{ title }}</p>'
    )
    assert _errors_in_primary_action(tmp_path) == {"page.html": 3}


def test_no_template_draws_an_error_in_the_primary_action_colour() -> None:
    """--color-primary-action is the brand crimson of the primary button; an error in it reads as brand, not error."""
    found = _errors_in_primary_action(config.get_templates_path())
    assert not found, (
        "Errors are drawn in the error tokens: messages in var(--color-error-text), field borders in "
        f"var(--color-error-border). Templates drawing an error in --color-primary-action: {found}"
    )

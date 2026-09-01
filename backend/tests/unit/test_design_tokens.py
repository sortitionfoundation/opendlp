"""ABOUTME: Guards against templates and CSS source referencing undefined CSS design tokens
ABOUTME: Every var(--...) must be defined in the backoffice token files (see issue #797)"""

import re
from pathlib import Path

from opendlp import config

TOKEN_FILES = (
    config.get_static_path() / "backoffice" / "tokens" / "primitive.css",
    config.get_static_path() / "backoffice" / "tokens" / "semantic.css",
)

DEFINITION_RE = re.compile(r"(--[a-z0-9-]+)\s*:")
REFERENCE_RE = re.compile(r"var\(\s*(--[a-z0-9-]+)")


def _defined_tokens() -> set[str]:
    defined: set[str] = set()
    for token_file in TOKEN_FILES:
        defined.update(DEFINITION_RE.findall(token_file.read_text()))
    return defined


def _find_undefined_refs(root: Path, defined: set[str], pattern: str = "*.html") -> dict[str, set[str]]:
    undefined_refs: dict[str, set[str]] = {}
    for template in sorted(root.rglob(pattern)):
        text = template.read_text()
        # Tokens a template defines inline (e.g. in a <style> block) are fine to reference.
        local = set(DEFINITION_RE.findall(text))
        for token in REFERENCE_RE.findall(text):
            if token not in defined and token not in local:
                undefined_refs.setdefault(token, set()).add(str(template.relative_to(root)))
    return undefined_refs


def test_token_files_exist_and_define_tokens() -> None:
    for token_file in TOKEN_FILES:
        assert token_file.is_file(), f"design token file missing: {token_file}"
    assert len(_defined_tokens()) > 50


def test_scan_detects_undefined_and_allows_defined_tokens(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text(
        '<a style="color: var(--color-bogus)">x</a>'
        '<p style="color: var(--color-known); background: var(--local)">y</p>'
        "<style>:root { --local: red; }</style>"
    )
    undefined_refs = _find_undefined_refs(tmp_path, {"--color-known"})
    assert undefined_refs == {"--color-bogus": {"page.html"}}


def test_templates_only_reference_defined_tokens() -> None:
    """An undefined var(--x) with no fallback silently resolves to the inherited value,
    so links render in body-text colour and status banners lose their background."""
    undefined_refs = _find_undefined_refs(config.get_templates_path(), _defined_tokens())
    assert not undefined_refs, (
        "Templates reference CSS custom properties that are not defined in "
        "static/backoffice/tokens/{primitive,semantic}.css - define the token (or an alias) "
        f"there, or repoint the template at an existing token: {undefined_refs}"
    )


def test_backoffice_css_source_only_references_defined_tokens() -> None:
    """The same trap as the templates, in the file the templates are styled from.

    Scanned as well as `templates/`: main.css is hand-written source (Tailwind
    compiles it into `dist/`), so an undefined token here fails just as silently.
    """
    css_source = config.get_static_path() / "backoffice" / "src"
    undefined_refs = _find_undefined_refs(css_source, _defined_tokens(), pattern="*.css")
    assert not undefined_refs, (
        "static/backoffice/src CSS references custom properties that are not defined in "
        "static/backoffice/tokens/{primitive,semantic}.css - define the token (or an alias) "
        f"there, or repoint the rule at an existing token: {undefined_refs}"
    )

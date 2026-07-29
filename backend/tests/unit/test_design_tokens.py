"""ABOUTME: Guards against templates referencing undefined CSS design tokens
ABOUTME: Every var(--...) in templates must be defined in the backoffice token files (see issue #797)"""

import re

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


def test_token_files_exist_and_define_tokens() -> None:
    for token_file in TOKEN_FILES:
        assert token_file.is_file(), f"design token file missing: {token_file}"
    assert len(_defined_tokens()) > 50


def test_templates_only_reference_defined_tokens() -> None:
    """An undefined var(--x) with no fallback silently resolves to the inherited value,
    so links render in body-text colour and status banners lose their background."""
    defined = _defined_tokens()
    undefined_refs: dict[str, set[str]] = {}
    for template in sorted(config.get_templates_path().rglob("*.html")):
        text = template.read_text()
        # Tokens a template defines inline (e.g. in a <style> block) are fine to reference.
        local = set(DEFINITION_RE.findall(text))
        for token in REFERENCE_RE.findall(text):
            if token not in defined and token not in local:
                undefined_refs.setdefault(token, set()).add(str(template.relative_to(config.get_templates_path())))
    assert not undefined_refs, (
        "Templates reference CSS custom properties that are not defined in "
        "static/backoffice/tokens/{primitive,semantic}.css - define the token (or an alias) "
        f"there, or repoint the template at an existing token: {undefined_refs}"
    )

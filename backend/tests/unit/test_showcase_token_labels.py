"""ABOUTME: Fails if a swatch on the showcase's Foundations tab prints a value its token does not have: a primitive's
ABOUTME: hex, or the primitive a semantic token points at. The labels are plain text and do not follow the tokens."""

import re
from pathlib import Path

from opendlp import config

TOKENS = config.get_static_path() / "backoffice" / "tokens"
SHOWCASE = config.get_templates_path() / "backoffice" / "showcase"

DEFINITION_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
# A primitive swatch: <div id="token-brand-700" ...> then its name and its hex as text.
PRIMITIVE_LABEL_RE = re.compile(
    r'<div id="token-([a-z0-9-]+)"[^>]*>\s*<p class="text-label-lg">\s*\1\s*</p>\s*'
    r'<p class="text-body-sm[^"]*">\s*(#[0-9A-Fa-f]{6})\s*</p>'
)
# A semantic swatch: the token's name, then "→ <primitive>" for the token it points at.
ALIAS_LABEL_RE = re.compile(
    r'<p[^>]*class="text-code"[^>]*>\s*(--[a-z0-9-]+)\s*</p>\s*<p[^>]*class="text-caption[^"]*"[^>]*>\s*→\s*([a-z0-9-]+)\s*</p>'
)


def _definitions(token_file: str) -> dict[str, str]:
    return {name: value.strip() for name, value in DEFINITION_RE.findall((TOKENS / token_file).read_text())}


def _read(template: str) -> str:
    return Path(SHOWCASE / template).read_text()


def test_the_primitive_swatches_print_their_tokens_hex() -> None:
    definitions = _definitions("primitive.css")
    labels = PRIMITIVE_LABEL_RE.findall(_read("primitive_tokens.html"))
    assert labels, "no primitive swatch found: has the Foundations markup changed?"
    stale = {
        name: printed for name, printed in labels if definitions.get(f"--color-{name}", "").upper() != printed.upper()
    }
    assert stale == {}


def test_the_semantic_swatches_name_the_primitive_their_token_points_at() -> None:
    definitions = _definitions("semantic.css")
    labels = ALIAS_LABEL_RE.findall(_read("semantic_tokens.html"))
    assert labels, "no semantic swatch with an arrow found: has the Foundations markup changed?"
    stale = {
        name: target
        for name, target in labels
        if definitions.get(name, "").replace(" ", "") != f"var(--color-{target})"
    }
    assert stale == {}

"""ABOUTME: Pins the link colour: both link tokens are link blue, the design's info-600
ABOUTME: so every link coloured through them shows in that blue, not the brand crimson"""

import re

from opendlp import config

SEMANTIC_TOKENS = config.get_static_path() / "backoffice" / "tokens" / "semantic.css"

DEFINITION_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _definitions() -> dict[str, str]:
    return {name: value.strip() for name, value in DEFINITION_RE.findall(SEMANTIC_TOKENS.read_text())}


def test_link_tokens_are_link_blue() -> None:
    definitions = _definitions()
    assert definitions["--color-links"] == "var(--color-info-600)"
    assert definitions["--color-link-text"] == "var(--color-info-600)"
    assert definitions["--color-info-600"].upper() == "#2B5FA6"

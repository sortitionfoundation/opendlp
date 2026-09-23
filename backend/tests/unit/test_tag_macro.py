"""ABOUTME: Jinja render tests for the tag macro
ABOUTME: Checks each colour maps onto its semantic token pair and an unknown one falls back to grey"""

import pytest
from flask import Flask, render_template_string

from opendlp import config


def _render(template: str) -> str:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    with app.test_request_context("/"):
        return render_template_string('{% from "backoffice/components/tag.html" import tag %}' + template)


@pytest.mark.parametrize(
    ("colour", "token"),
    [
        ("grey", "subtle-background-panels"),
        ("blue", "info-background"),
        ("green", "success-background"),
        ("yellow", "warning-background"),
        ("red", "error-background"),
        ("purple", "subtle-background-panels"),
    ],
)
def test_each_colour_uses_its_semantic_tokens(colour, token):
    html = _render('{{ tag("Destructive action", colour="' + colour + '") }}')

    assert f"background-color: var(--color-{token})" in html
    assert ">Destructive action</strong>" in html
    assert "govuk-tag" not in html

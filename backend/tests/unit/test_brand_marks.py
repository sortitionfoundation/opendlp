"""ABOUTME: Jinja render tests for the Google and Microsoft marks in components/brand_marks.html
ABOUTME: The marks must switch off the stroke a button's icon slot gives its svg, or every shape is outlined"""

import re

import pytest
from flask import Flask, render_template_string

from opendlp import config


def _render(macro: str) -> str:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    with app.test_request_context("/"):
        return render_template_string(f'{{% from "components/brand_marks.html" import {macro} %}}{{{{ {macro}() }}}}')


@pytest.mark.parametrize("macro", ["brand_google", "brand_microsoft"])
def test_the_mark_turns_off_the_inherited_stroke(macro: str) -> None:
    """`.btn-icon svg` in main.css strokes the svg with currentColor for the Lucide icons.

    The marks' paths inherited it, which outlined each shape and boxed the Google
    G. Only an inline style on the svg outranks that rule, so it has to be there.
    """
    svg = re.search(r"<svg\b[^>]*>", _render(macro))

    assert svg is not None
    assert re.search(r'style="[^"]*\bstroke: none\b', svg.group(0))


@pytest.mark.parametrize("macro", ["brand_google", "brand_microsoft"])
def test_no_path_sets_a_stroke_of_its_own(macro: str) -> None:
    """The vendors draw their marks with fills only, so nothing should bring a stroke back."""
    paths = re.findall(r"<path\b[^>]*>", _render(macro))

    assert paths
    assert not [path for path in paths if "stroke" in path]

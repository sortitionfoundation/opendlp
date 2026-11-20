"""ABOUTME: Jinja render tests for the stat_tile macro
ABOUTME: Checks the label and number render, the number is not a heading, and the id is optional"""

from flask import Flask, render_template_string

from opendlp import config


def _render(template: str) -> str:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    with app.test_request_context("/"):
        return render_template_string('{% from "backoffice/components/stat_tile.html" import stat_tile %}' + template)


def test_renders_label_and_value():
    """The label and the number both appear, the number in the large display style."""
    html = _render('{{ stat_tile("Total users", 42) }}')

    assert ">Total users</p>" in html
    assert 'class="text-display-sm mt-1"' in html
    assert ">42</p>" in html


def test_number_is_not_a_heading():
    """A row of tiles must not add entries to the page's heading outline."""
    html = _render('{{ stat_tile("Admins", 3) }}')

    assert "<h" not in html


def test_id_only_rendered_when_given():
    """An id attribute appears only when the caller asks for one."""
    assert 'id="' not in _render('{{ stat_tile("Admins", 3) }}')
    assert 'id="admin-count"' in _render('{{ stat_tile("Admins", 3, id="admin-count") }}')

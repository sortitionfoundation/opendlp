"""ABOUTME: Jinja render tests for the alert macro's message and caller content.
ABOUTME: Verifies a caller's content is not wrapped in a paragraph, which cannot hold a list."""

from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext


def _render(template: str) -> str:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.jinja_env.globals["_"] = gettext
    with app.test_request_context("/"):
        return render_template_string('{% from "backoffice/components/alert.html" import alert %}' + template)


class TestAlertContent:
    def test_a_message_is_a_paragraph_that_keeps_its_line_breaks(self):
        html = _render('{{ alert("first line\\nsecond line", variant="warning") }}')

        assert "<p " in html
        assert "white-space: pre-line" in html
        assert ">first line\nsecond line</p>" in html

    def test_a_callers_content_is_not_wrapped_in_a_paragraph(self):
        """A <p> cannot hold a list: the browser would close it, empty, before the list, and it would still take up room."""
        html = _render(
            '{% call alert(variant="warning", use_caller=true) %}<p>Before:</p><ul><li>One</li></ul>{% endcall %}'
        )

        assert html.count("<p") == 1
        assert '<div class="text-body-md flex-1"' in html
        assert "<p>Before:</p><ul><li>One</li></ul></div>" in html

    def test_a_callers_content_does_not_turn_template_line_breaks_into_blank_lines(self):
        html = _render("{% call alert(use_caller=true) %}\n<ul>\n<li>One</li>\n</ul>\n{% endcall %}")

        assert "pre-line" not in html

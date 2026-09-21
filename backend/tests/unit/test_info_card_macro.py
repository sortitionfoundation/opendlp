"""ABOUTME: Jinja render tests for the info_card macro
ABOUTME: Checks the icon, the optional heading and that the caller's content lands inside the card"""

from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext


def _render(template: str) -> str:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.jinja_env.globals["_"] = gettext
    with app.test_request_context("/"):
        return render_template_string('{% from "backoffice/components/info_card.html" import info_card %}' + template)


class TestInfoCard:
    def test_renders_the_heading_and_the_callers_content(self):
        html = _render('{% call info_card(title="Targets live elsewhere") %}<p id="body">Go there</p>{% endcall %}')

        assert '<h2 class="text-heading-md mb-2"' in html
        assert "Targets live elsewhere</h2>" in html
        assert '<p id="body">Go there</p>' in html
        assert html.index("</h2>") < html.index('<p id="body">')
        assert "<svg" in html

    def test_has_no_heading_without_a_title(self):
        html = _render('{% call info_card() %}<p id="body">Go there</p>{% endcall %}')

        assert "<h2" not in html
        assert '<p id="body">Go there</p>' in html

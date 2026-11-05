"""ABOUTME: Jinja render tests for the info_icon macro in backoffice/components/info_icon.html
ABOUTME: Covers the toggletip's button and its name, the live region, the bubble and the no-JavaScript title"""

import re

from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext

TEXT = "Withdrawn people are not counted."


def _render(macro_call: str) -> str:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    with app.test_request_context("/"):
        return render_template_string(
            '{% from "backoffice/components/info_icon.html" import info_icon %}' + macro_call,
        )


def _button(html: str) -> str:
    match = re.search(r"<button\b[^>]*>", html)
    assert match is not None
    return match.group(0)


class TestInfoIcon:
    def test_is_a_real_button_wired_to_the_toggletip_component(self):
        html = _render(f'{{{{ info_icon("{TEXT}") }}}}')

        assert 'x-data="infoToggletip"' in html
        button = _button(html)
        assert 'type="button"' in button
        assert '@click="toggle"' in button

    def test_the_button_is_named_after_what_it_explains(self):
        html = _render(f'{{{{ info_icon("{TEXT}", about="Registrations") }}}}')

        assert 'aria-label="More about Registrations"' in _button(html)

    def test_without_about_the_button_has_a_general_name(self):
        html = _render(f'{{{{ info_icon("{TEXT}") }}}}')

        assert 'aria-label="More information"' in _button(html)

    def test_the_text_is_in_a_popover_bubble_hidden_from_screen_readers(self):
        html = _render(f'{{{{ info_icon("{TEXT}", id="withdrawn-info") }}}}')

        bubble = re.search(r'<span ([^>]*) id="withdrawn-info">([^<]*)</span>', html)
        assert bubble is not None
        assert 'popover="manual"' in bubble.group(1)
        assert 'aria-hidden="true"' in bubble.group(1)
        assert 'x-ref="bubble"' in bubble.group(1)
        assert bubble.group(2) == TEXT

    def test_the_text_is_announced_through_a_live_region(self):
        html = _render(f'{{{{ info_icon("{TEXT}") }}}}')

        assert re.search(r'<span role="status"[^>]*x-text="announced"[^>]*></span>', html)

    def test_without_javascript_the_text_is_the_buttons_title(self):
        html = _render(f'{{{{ info_icon("{TEXT}") }}}}')

        button = _button(html)
        assert f'title="{TEXT}"' in button
        # The component binds the title away, so a mouse user does not see the text twice.
        assert ':title="nativeTitle"' in button

    def test_without_an_id_the_bubble_has_none(self):
        html = _render(f'{{{{ info_icon("{TEXT}") }}}}')

        assert " id=" not in html

    def test_closes_on_escape_a_click_outside_and_focus_leaving(self):
        html = _render(f'{{{{ info_icon("{TEXT}") }}}}')

        assert '@keydown.escape="closeOnEscape"' in html
        assert '@click.outside="close"' in html
        assert '@focusout="closeOnFocusOut"' in html

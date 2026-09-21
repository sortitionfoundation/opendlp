"""ABOUTME: Jinja render tests for how the menu and modal macros take the Escape key
ABOUTME: Menus claim it on their own element, so dialog-escape.js on window never closes the dialog around them"""

import re

from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext


def _make_app() -> Flask:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    return app


def _render(template: str) -> str:
    app = _make_app()
    with app.test_request_context("/"):
        return render_template_string(template)


class TestDropdownButton:
    def _html(self, disabled: bool = False) -> str:
        return _render(
            '{% from "backoffice/components/dropdown_button.html" import dropdown_button %}'
            '{{ dropdown_button(label="Change status", id="status", disabled=' + str(disabled).lower() + ","
            ' items=[{"text": "Publish"}, {"text": "Close"}]) }}'
        )

    def test_is_a_menu_button_that_takes_escape_on_its_own_element(self):
        html = self._html()

        assert 'x-data="menuButton"' in html
        assert '@keydown.escape="closeOnEscape"' in html
        assert "escape.window" not in html
        assert '@focusout="closeOnFocusOut"' in html

    def test_the_arrow_keys_are_wired_on_the_toggle_and_the_menu(self):
        html = self._html()

        toggle = re.search(r'<button type="button"\s+id="status-toggle"[^>]*>', html)
        assert toggle is not None
        assert 'x-ref="menuToggle"' in toggle.group(0)
        assert '@keydown="onToggleKeydown"' in toggle.group(0)
        menu = re.search(r'<div[^>]*id="status-menu"[^>]*>', html)
        assert menu is not None
        assert 'x-ref="menu"' in menu.group(0)
        assert '@keydown="onMenuKeydown"' in menu.group(0)

    def test_the_menu_is_one_tab_stop(self):
        items = re.findall(r'<button[^>]*role="menuitem"[^>]*>', self._html())

        assert len(items) == 2
        assert all('tabindex="-1"' in item for item in items)

    def test_a_disabled_trigger_cannot_open_the_menu(self):
        html = self._html(disabled=True)

        toggle = re.search(r'<button type="button"\s+id="status-toggle"[^>]*>', html)
        assert toggle is not None
        assert "disabled" in toggle.group(0)
        assert "toggleMenu" not in toggle.group(0)


class TestAccountMenu:
    def test_takes_escape_on_its_own_element(self):
        html = _render(
            '{% from "backoffice/components/account_menu.html" import account_menu %}'
            '{{ account_menu(initials="AB", id="account", items=[{"label": "Profile", "href": "/profile"}]) }}'
        )

        assert '@keydown.escape="closeOnEscape"' in html
        assert "escape.window" not in html
        assert 'x-ref="menuToggle"' in html


class TestModals:
    """Each modal stops an Escape pressed inside it, and keeps a window listener for one pressed elsewhere."""

    def test_the_alpine_modals_stop_escape_inside_them(self):
        html = _render(
            '{% from "backoffice/components/modal.html" import alert_dialog, modal %}'
            '{% call alert_dialog(id="a", title="Sure?") %}<button>OK</button>{% endcall %}'
            '{% call modal(id="m", title="Details") %}<p>Body</p>{% endcall %}'
        )

        positioners = re.findall(r'<div[^>]*class="dialog-positioner"[^>]*>', html)
        assert len(positioners) == 2
        assert all('@keydown.escape.stop="closeIfAllowed()"' in p for p in positioners)
        assert html.count('@keydown.escape.window="closeIfAllowed()"') == 2

    def test_the_controlled_modals_stop_escape_inside_them(self):
        html = _render(
            '{% from "backoffice/components/modal.html" import controlled_alert_dialog, controlled_modal %}'
            '{% call controlled_alert_dialog(id="a", title="Sure?", description="", open_expr="aOpen",'
            ' close_expr="closeA()") %}<button>OK</button>{% endcall %}'
            '{% call controlled_modal(id="m", title="Details", open_expr="mOpen", close_expr="closeM()") %}'
            "<p>Body</p>{% endcall %}"
        )

        positioners = re.findall(r'<div[^>]*class="dialog-positioner"[^>]*>', html)
        assert len(positioners) == 2
        assert '@keydown.escape.stop="closeA()"' in positioners[0]
        assert '@keydown.escape.stop="closeM()"' in positioners[1]
        assert '@keydown.escape.window="closeA()"' in html
        assert '@keydown.escape.window="closeM()"' in html

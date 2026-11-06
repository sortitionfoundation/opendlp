# ABOUTME: Component tests for the headings and text placed among the registration questions
# ABOUTME: Drives the real backoffice routes for adding, editing, moving and removing them over a fake store

import re

import pytest

from opendlp.domain.registration_content_block import RegistrationContentBlock, form_item_ref
from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer import respondent_field_schema_service
from opendlp.service_layer.user_service import grant_user_assembly_role
from tests.fakes import FakeUnitOfWork

HTMX = {"HX-Request": "true"}


def _base(assembly) -> str:
    return f"/backoffice/project/{assembly.id}/respondent-schema"


@pytest.fixture
def schema(fake_store, admin_user, existing_assembly):
    with FakeUnitOfWork(store=fake_store) as uow:
        respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, existing_assembly.id)
        uow.commit()


def _block(
    fake_store, admin_user, assembly, heading: str = "About you", body_html: str = ""
) -> RegistrationContentBlock:
    with FakeUnitOfWork(store=fake_store) as uow:
        block = respondent_field_schema_service.add_content_block(
            uow, admin_user.id, assembly.id, heading=heading, body_html=body_html
        )
        uow.commit()
        return block


def _layout(fake_store, admin_user, assembly) -> list[str]:
    with FakeUnitOfWork(store=fake_store) as uow:
        items = respondent_field_schema_service.get_form_items(uow, admin_user.id, assembly.id)
    return [f"# {i.heading}" if isinstance(i, RegistrationContentBlock) else i.field_key for i in items]


@pytest.mark.usefixtures("schema")
class TestTheList:
    def test_a_block_has_its_own_row_with_its_heading_and_kind(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        block = _block(fake_store, admin_user, existing_assembly, "About you", "<p>Tell us about yourself.</p>")

        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        row = re.search(r'<tr class="content-block-row"[^>]*>(.*?)</tr>', body, re.DOTALL)
        assert row is not None
        assert '<div class="content-block-row__heading">About you</div>' in row.group(1)
        assert "Tell us about yourself." in row.group(1)
        assert ">Heading and text<" in row.group(1)
        assert f'href="{_base(existing_assembly)}/blocks/{block.id}/edit-modal"' in row.group(1)
        assert f"/blocks/{block.id}/delete" in row.group(1)

    @pytest.mark.parametrize(
        ("heading", "body_html", "kind"),
        [("Consent", "", "Heading"), ("", "<p>Read the notes first.</p>", "Text")],
    )
    def test_a_block_with_only_a_heading_or_only_text_says_so(
        self, logged_in_admin, existing_assembly, admin_user, fake_store, heading, body_html, kind
    ):
        _block(fake_store, admin_user, existing_assembly, heading, body_html)

        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        row = re.search(r'<tr class="content-block-row"[^>]*>(.*?)</tr>', body, re.DOTALL)
        assert re.search(
            rf'<div class="content-block-row__kind[^"]*">.*</svg>\s*<span>{kind}</span></div>', row.group(1), re.DOTALL
        )

    def test_a_text_question_is_short_text_so_it_is_not_confused_with_a_text_block(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """A question asking for text and a block holding only text must not share a label."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.add_field(uow, admin_user.id, existing_assembly.id, "first_name")
            uow.commit()
        _block(fake_store, admin_user, existing_assembly, "", "<p>Read the notes first.</p>")

        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        question = re.search(r'<tr class="question-row"[^>]*>(?:(?!</tr>).)*first_name.*?</tr>', body, re.DOTALL)
        block = re.search(r'<tr class="content-block-row"[^>]*>(.*?)</tr>', body, re.DOTALL)
        assert '<div class="text-body-md">Short text</div>' in question.group(0)
        assert "<span>Text</span></div>" in block.group(1)

    def test_a_block_type_carries_a_decorative_text_icon_and_a_question_does_not(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The icon marks blocks out at a glance; the word beside it is what is announced."""
        _block(fake_store, admin_user, existing_assembly, "About you")

        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        block = re.search(r'<tr class="content-block-row"[^>]*>(.*?)</tr>', body, re.DOTALL).group(1)
        kind = re.search(r'<div class="content-block-row__kind[^"]*">(.*?)</div>', block, re.DOTALL)
        assert kind is not None
        assert re.search(r'<svg[^>]*aria-hidden="true"', kind.group(1))
        assert kind.group(1).rstrip().endswith("<span>Heading</span>")
        questions = re.findall(r'<tr class="question-row"[^>]*>.*?</tr>', body, re.DOTALL)
        assert questions
        assert not any("content-block-row__kind" in question for question in questions)

    def test_the_column_headers_are_for_screen_readers_only(self, logged_in_admin, existing_assembly):
        """The cards explain themselves on screen; the headers stay so each cell is announced with its column."""
        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        thead = re.search(r"<thead>(.*?)</thead>", body, re.DOTALL).group(1)
        headers = re.findall(r'<th scope="col">\s*<span class="sr-only">([^<]*)</span>\s*</th>', thead)
        assert headers == ["Item", "Type", "Notes", "Actions"]

    def test_a_text_only_block_is_named_by_its_first_line(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _block(fake_store, admin_user, existing_assembly, "", "<p>Read the notes first.</p><p>Then answer.</p>")

        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        assert 'aria-label="Edit Read the notes first."' in body


@pytest.mark.usefixtures("schema")
class TestTheDialog:
    def test_new_dialog_has_a_heading_and_a_compact_visual_editor(self, logged_in_admin, existing_assembly):
        body = logged_in_admin.get(f"{_base(existing_assembly)}/blocks/new-modal", headers=HTMX).get_data(as_text=True)

        assert "Add a heading or text" in body
        assert 'id="block-modal-heading"' in body
        assert re.search(r'<textarea[^>]*id="block-modal-body"[^>]*data-rich-editor', body, re.DOTALL)
        assert 'data-command="heading3"' in body
        assert 'data-command="alignCenter"' in body
        for left_out in ("heading1", "heading2", "underline", "strike", "blockquote", "horizontalRule", "image"):
            assert f'data-command="{left_out}"' not in body
        assert 'data-command="table"' not in body

    def test_new_dialog_carries_its_own_link_dialog(self, logged_in_admin, existing_assembly):
        """The questions step is not the registration editor, so the Link button needs a dialog here."""
        body = logged_in_admin.get(f"{_base(existing_assembly)}/blocks/new-modal", headers=HTMX).get_data(as_text=True)

        assert 'x-data="richEditorLinkHost"' in body
        assert '@rich-editor-link-request.document="openLinkDialog($event)"' in body
        assert 'id="link-modal-url"' in body
        assert 'id="rich-editor-link-data"' in body
        assert "Enter a link address" in body

    def test_new_dialog_opened_below_a_row_remembers_it(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        block = _block(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{_base(existing_assembly)}/blocks/new-modal",
            query_string={"after": f"block:{block.id}"},
            headers=HTMX,
        ).get_data(as_text=True)

        assert f'<input type="hidden" name="after" value="block:{block.id}">' in body

    def test_without_javascript_the_dialog_opens_over_the_page(self, logged_in_admin, existing_assembly):
        body = logged_in_admin.get(f"{_base(existing_assembly)}/blocks/new-modal").get_data(as_text=True)

        assert "<html" in body
        assert 'aria-labelledby="block-modal-title"' in body

    def test_the_page_loads_the_editor_script_and_styles(self, logged_in_admin, existing_assembly):
        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        assert "backoffice/js/dist/html-editor.js" in body
        assert "css/rich-editor.css" in body

    def test_edit_dialog_is_filled_in(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        block = _block(fake_store, admin_user, existing_assembly, "About you", "<p>Hello</p>")

        body = logged_in_admin.get(f"{_base(existing_assembly)}/blocks/{block.id}/edit-modal", headers=HTMX).get_data(
            as_text=True
        )

        assert "Edit heading or text" in body
        assert 'value="About you"' in body
        assert "&lt;p&gt;Hello&lt;/p&gt;" in body
        assert f'action="{_base(existing_assembly)}/blocks/{block.id}/update"' in body


@pytest.mark.usefixtures("schema")
class TestSaving:
    def test_add_saves_the_block_at_the_end_and_closes_the_dialog(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/blocks/add",
            data={"heading": "The small print", "body_html": "<p>We keep your data safe.</p>", "after": ""},
            headers=HTMX,
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'id="schema-editor" hx-swap-oob="true"' in body
        assert "The small print" in body
        assert _layout(fake_store, admin_user, existing_assembly)[-1] == "# The small print"

    def test_add_below_a_row_puts_it_there(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            email = uow.respondent_field_definitions.get_by_assembly_and_key(existing_assembly.id, "email")
            email_id = email.id

        logged_in_admin.post(
            f"{_base(existing_assembly)}/blocks/add",
            data={"heading": "Consent", "body_html": "", "after": f"question:{email_id}"},
            headers=HTMX,
        )

        layout = _layout(fake_store, admin_user, existing_assembly)
        assert layout[layout.index("email") + 1] == "# Consent"

    def test_an_empty_block_reopens_the_dialog_with_an_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/blocks/add",
            data={"heading": " ", "body_html": "<p></p>"},
            headers=HTMX,
        )

        assert response.status_code == 422
        body = response.get_data(as_text=True)
        assert "Add a heading, some text, or both" in body
        assert 'aria-labelledby="block-modal-title"' in body

    def test_without_javascript_add_redirects_with_a_message(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/blocks/add", data={"heading": "About you"}, follow_redirects=True
        )

        assert response.status_code == 200
        assert "Heading or text added" in response.get_data(as_text=True)

    def test_update_saves_the_new_content(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        block = _block(fake_store, admin_user, existing_assembly, "Old")

        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/blocks/{block.id}/update",
            data={"heading": "New", "body_html": "<ul><li>One</li></ul>"},
            headers=HTMX,
        )

        assert response.status_code == 200
        with FakeUnitOfWork(store=fake_store) as uow:
            saved = uow.registration_content_blocks.get(block.id)
            assert (saved.heading, saved.body_html) == ("New", "<ul><li>One</li></ul>")

    def test_update_keeps_any_html_typed_in_the_html_view(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Only the toolbar is short: what someone writes in the HTML view is theirs to keep."""
        block = _block(fake_store, admin_user, existing_assembly, "Old")
        html = '<h1>Big</h1><table><tr><td>x</td></tr></table><img src="/a.png" alt="">'

        logged_in_admin.post(
            f"{_base(existing_assembly)}/blocks/{block.id}/update",
            data={"heading": "Old", "body_html": html},
            headers=HTMX,
        )

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_content_blocks.get(block.id).body_html == html

    def test_update_of_a_block_that_has_gone_shows_the_list(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        block = _block(fake_store, admin_user, existing_assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.delete_content_block(uow, admin_user.id, existing_assembly.id, block.id)
            uow.commit()

        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/blocks/{block.id}/update",
            data={"heading": "Too late"},
            headers=HTMX,
        )

        assert response.status_code == 200
        assert 'id="schema-editor" hx-swap-oob="true"' in response.get_data(as_text=True)

    def test_delete_removes_it(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        block = _block(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(f"{_base(existing_assembly)}/blocks/{block.id}/delete", follow_redirects=True)

        assert "Heading or text removed" in response.get_data(as_text=True)
        assert "# About you" not in _layout(fake_store, admin_user, existing_assembly)

    def test_move_to_top(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _block(fake_store, admin_user, existing_assembly, "Start")
        block_id = next(b.id for b in fake_store.registration_content_blocks.list_by_assembly(existing_assembly.id))

        response = logged_in_admin.post(f"{_base(existing_assembly)}/blocks/{block_id}/move", data={"direction": "top"})

        assert response.status_code == 302
        assert _layout(fake_store, admin_user, existing_assembly)[0] == "# Start"

    def test_a_question_moves_to_the_bottom(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            email_id = uow.respondent_field_definitions.get_by_assembly_and_key(existing_assembly.id, "email").id

        logged_in_admin.post(f"{_base(existing_assembly)}/fields/{email_id}/move", data={"direction": "bottom"})

        assert _layout(fake_store, admin_user, existing_assembly)[-1] == "email"


@pytest.mark.usefixtures("schema")
class TestPermissions:
    def test_a_read_only_viewer_cannot_add_a_block(
        self, logged_in_user, regular_user, existing_assembly, admin_user, fake_store
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=regular_user.id,
                assembly_id=existing_assembly.id,
                role=AssemblyRole.READ_ONLY,
                current_user=admin_user,
            )

        response = logged_in_user.post(
            f"{_base(existing_assembly)}/blocks/add", data={"heading": "Sneaky"}, headers=HTMX
        )

        assert response.status_code == 422
        assert "You don&#39;t have permission to edit the schema" in response.get_data(as_text=True)
        assert _layout(fake_store, admin_user, existing_assembly).count("# Sneaky") == 0


@pytest.mark.usefixtures("schema")
class TestReorder:
    def _refs(self, fake_store, admin_user, assembly) -> list[str]:
        with FakeUnitOfWork(store=fake_store) as uow:
            items = respondent_field_schema_service.get_form_items(uow, admin_user.id, assembly.id)
        return [form_item_ref(item).form_value for item in items]

    def test_each_row_carries_its_place_for_the_reorder_form(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        block = _block(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        assert re.search(r'<form id="reorder-form"[^>]*hx-post="[^"]*/respondent-schema/reorder"', body)
        assert f'<input type="hidden" name="item" value="block:{block.id}" form="reorder-form">' in body
        assert body.count('name="item"') == len(self._refs(fake_store, admin_user, existing_assembly))

    def test_drag_handles_are_hidden_from_assistive_technology(self, logged_in_admin, existing_assembly):
        """Dragging is a pointer shortcut; the row menu's move commands are the accessible route."""
        body = logged_in_admin.get(_base(existing_assembly)).get_data(as_text=True)

        handles = re.findall(r"<span[^>]*data-drag-handle[^>]*>", body)
        assert handles
        assert all('aria-hidden="true"' in handle for handle in handles)
        assert 'x-data="sortableRows"' in body

    def test_reorder_saves_the_new_order_and_redraws_the_list(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        refs = self._refs(fake_store, admin_user, existing_assembly)
        reversed_refs = list(reversed(refs))

        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/reorder", data={"item": reversed_refs}, headers=HTMX
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert '<div id="schema-editor"' in body
        assert "Order saved" in body
        assert self._refs(fake_store, admin_user, existing_assembly) == reversed_refs

    def test_an_order_from_a_stale_page_is_refused_and_the_list_redrawn(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        refs = self._refs(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(f"{_base(existing_assembly)}/reorder", data={"item": refs[1:]}, headers=HTMX)

        # 422, the status the page's HTMX set-up swaps in rather than drops
        assert response.status_code == 422
        body = response.get_data(as_text=True)
        assert "The questions have changed since this page was loaded" in body
        assert '<div id="schema-editor"' in body
        assert self._refs(fake_store, admin_user, existing_assembly) == refs

    def test_without_javascript_reorder_redirects(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        refs = self._refs(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(f"{_base(existing_assembly)}/reorder", data={"item": list(reversed(refs))})

        assert response.status_code == 302

    def test_a_menu_move_says_where_it_landed_and_comes_back_to_the_menu(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            email_id = uow.respondent_field_definitions.get_by_assembly_and_key(existing_assembly.id, "email").id
        total = len(self._refs(fake_store, admin_user, existing_assembly))

        response = logged_in_admin.post(f"{_base(existing_assembly)}/fields/{email_id}/move", data={"direction": "top"})

        assert response.location.endswith(f"#focus=item-actions-{email_id}-toggle")
        page = logged_in_admin.get(response.location.split("#")[0]).get_data(as_text=True)
        assert f"Moved to position 1 of {total}" in page
        assert f'data-focus-id="item-actions-{email_id}-toggle"' in page

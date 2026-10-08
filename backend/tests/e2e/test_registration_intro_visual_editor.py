"""ABOUTME: E2E tests for the registration intro's visual editor, over PostgreSQL
ABOUTME: The intro step renders the editor's controls, and the HTML it produces is saved and served verbatim"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_page_service import page_for_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

# What the visual editor writes back for a heading, formatted text, a link,
# a list and an image - the shape the toolbar produces, not hand-written HTML.
VISUAL_EDITOR_HTML = (
    "<h2><strong>Welcome to {{ assembly_title }}</strong></h2>"
    '<p>Read <a href="https://example.org/info">the information pack</a> first.</p>'
    "<ul><li><p>Two weekends</p></li><li><p><em>Paid</em> for your time</p></li></ul>"
    '<p><img src="/register-assets/images/00000000-0000-4000-8000-000000000000.png" alt="Logo"></p>'
)


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


@pytest.fixture
def registration_page(logged_in_admin, admin_user, postgres_session_factory):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Visual Editor Assembly",
            created_by_user_id=admin_user.id,
            question="Does the visual editor save what it shows?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id
    response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/create")
    assert response.status_code == 302
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, assembly_id)
        assert page is not None
        return assembly_id, page.id, page.url_slug


def _intro_step(client, assembly_id, slug, edit: bool) -> str:
    suffix = "&edit=1" if edit else ""
    response = client.get(f"/backoffice/assembly/{assembly_id}/registration/{slug}?section=intro{suffix}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_intro_step_renders_the_visual_editor_with_toolbar_and_images(logged_in_admin, registration_page):
    """In edit mode the intro textarea is marked for the visual editor, with images, a toolbar and Insert buttons."""
    assembly_id, _page_id, slug = registration_page

    body = _intro_step(logged_in_admin, assembly_id, slug, edit=True)

    assert 'data-rich-editor-for="intro_content"' in body
    assert "data-rich-editor " in body
    assert 'data-rich-editor-images="true"' in body
    assert 'role="toolbar"' in body
    assert 'data-command="image"' in body
    assert 'aria-controls="intro_content-visual"' in body
    assert "insertImage(image)" in body


def test_read_only_intro_step_has_no_toolbar(logged_in_admin, registration_page):
    """Outside edit mode the editor is shown read-only, so there is nothing to format with."""
    assembly_id, _page_id, slug = registration_page

    body = _intro_step(logged_in_admin, assembly_id, slug, edit=False)

    assert 'data-rich-editor-for="intro_content"' in body
    assert 'role="toolbar"' not in body


def test_visual_editor_html_is_saved_verbatim_and_rendered_publicly(
    logged_in_admin, client, registration_page, postgres_session_factory
):
    """The server stores exactly what the editor sends, and the public page renders it with variables filled in."""
    assembly_id, page_id, slug = registration_page

    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/save",
        data={"action": "save", "intro_content": VISUAL_EDITOR_HTML},
    )
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        html = uow.registration_page_html_sources.get_by_page_id(page_id)
        assert html is not None
        assert html.intro_html == VISUAL_EDITOR_HTML

    # A new page uses the GOV.UK content style, so the rendered intro gains default classes.
    public = client.get(f"/register/{slug}").get_data(as_text=True)
    assert '<h2 class="govuk-heading-l"><strong>Welcome to Visual Editor Assembly</strong></h2>' in public
    assert '<a class="govuk-link" href="https://example.org/info">the information pack</a>' in public


def _save_intro(client, assembly_id, slug, intro: str, content_style: str = "") -> None:
    data = {"action": "save", "intro_content": intro}
    if content_style:
        data["content_style"] = content_style
    response = client.post(f"/backoffice/assembly/{assembly_id}/registration/{slug}/save", data=data)
    assert response.status_code == 302


def _stored_style(postgres_session_factory, page_id) -> str:
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        html = uow.registration_page_html_sources.get_by_page_id(page_id)
        assert html is not None
        return html.content_style.value


def test_intro_step_offers_the_content_style_with_govuk_chosen_for_a_new_page(logged_in_admin, registration_page):
    assembly_id, _page_id, slug = registration_page

    body = _intro_step(logged_in_admin, assembly_id, slug, edit=True)

    assert 'name="content_style"' in body
    assert 'value="govuk"' in body and 'value="plain"' in body
    assert 'data-content-style="govuk"' in body
    assert "GOV.UK (recommended, accessible)" in body


def test_saving_the_intro_saves_the_chosen_style(logged_in_admin, registration_page, postgres_session_factory):
    assembly_id, page_id, slug = registration_page

    _save_intro(logged_in_admin, assembly_id, slug, "<h1>Hi</h1>", content_style="plain")

    assert _stored_style(postgres_session_factory, page_id) == "plain"


def test_a_post_without_a_style_leaves_it_alone(logged_in_admin, registration_page, postgres_session_factory):
    assembly_id, page_id, slug = registration_page
    _save_intro(logged_in_admin, assembly_id, slug, "<h1>Hi</h1>", content_style="plain")

    _save_intro(logged_in_admin, assembly_id, slug, "<h1>Hello</h1>")

    assert _stored_style(postgres_session_factory, page_id) == "plain"


def test_public_page_has_govuk_classes_only_under_the_govuk_style(
    logged_in_admin, client, registration_page, postgres_session_factory
):
    assembly_id, _page_id, slug = registration_page
    intro = '<h1>Title</h1><p class="lead">Mine</p><p>Body</p>'

    _save_intro(logged_in_admin, assembly_id, slug, intro, content_style="govuk")
    govuk = client.get(f"/register/{slug}").get_data(as_text=True)
    assert '<h1 class="govuk-heading-xl">Title</h1><p class="lead">Mine</p><p class="govuk-body">Body</p>' in govuk

    _save_intro(logged_in_admin, assembly_id, slug, intro, content_style="plain")
    plain = client.get(f"/register/{slug}").get_data(as_text=True)
    assert intro in plain


def test_a_page_from_before_content_styles_renders_unchanged(
    logged_in_admin, client, registration_page, postgres_session_factory
):
    """Rows that existed before the column get its server default, plain, so a live page does not change."""
    assembly_id, page_id, slug = registration_page
    _save_intro(logged_in_admin, assembly_id, slug, "<h1>Title</h1><p>Body</p>")
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.session.execute(
            text("UPDATE registration_page_html_sources SET content_style = DEFAULT WHERE registration_page_id = :id"),
            {"id": page_id},
        )
        uow.commit()

    assert _stored_style(postgres_session_factory, page_id) == "plain"
    assert "<h1>Title</h1><p>Body</p>" in client.get(f"/register/{slug}").get_data(as_text=True)

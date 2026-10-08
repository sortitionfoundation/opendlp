"""ABOUTME: E2E tests for the registration intro's visual editor, over PostgreSQL
ABOUTME: The intro step renders the editor's controls, and the HTML it produces is saved and served verbatim"""

from datetime import UTC, datetime, timedelta

import pytest

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

    public = client.get(f"/register/{slug}").get_data(as_text=True)
    assert "<h2><strong>Welcome to Visual Editor Assembly</strong></h2>" in public
    assert '<a href="https://example.org/info">the information pack</a>' in public

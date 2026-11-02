"""ABOUTME: E2E tests for the registration intro's visual editor, over PostgreSQL
ABOUTME: The HTML the editor produces is saved verbatim, and the public page renders it in its content style"""

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
def visitor(app):
    """A second, signed-out client: what a member of the public sees of the page."""
    return app.test_client()


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
    response = logged_in_admin.post(f"/backoffice/project/{assembly_id}/registration/create")
    assert response.status_code == 302
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, assembly_id)
        assert page is not None
        return assembly_id, page.id, page.url_slug


def test_visual_editor_html_is_saved_verbatim_and_rendered_publicly(
    logged_in_admin, visitor, registration_page, postgres_session_factory
):
    """The server stores exactly what the editor sends, and the public page renders it with variables filled in."""
    assembly_id, page_id, slug = registration_page

    response = logged_in_admin.post(
        f"/backoffice/project/{assembly_id}/registration/{slug}/save",
        data={"action": "save", "intro_content": VISUAL_EDITOR_HTML},
    )
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        html = uow.registration_page_html_sources.get_by_page_id(page_id)
        assert html is not None
        assert html.intro_html == VISUAL_EDITOR_HTML

    # A new page uses the GOV.UK content style, so the rendered intro gains default classes.
    public = visitor.get(f"/register/{slug}").get_data(as_text=True)
    assert '<h2 class="govuk-heading-l"><strong>Welcome to Visual Editor Assembly</strong></h2>' in public
    assert '<a class="govuk-link" href="https://example.org/info">the information pack</a>' in public


def _save_intro(client, assembly_id, slug, intro: str, content_style: str = "") -> None:
    data = {"action": "save", "intro_content": intro}
    if content_style:
        data["content_style"] = content_style
    response = client.post(f"/backoffice/project/{assembly_id}/registration/{slug}/save", data=data)
    assert response.status_code == 302


def _stored_style(postgres_session_factory, page_id) -> str:
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        html = uow.registration_page_html_sources.get_by_page_id(page_id)
        assert html is not None
        return html.content_style.value


def test_public_page_has_govuk_classes_only_under_the_govuk_style(logged_in_admin, visitor, registration_page):
    assembly_id, _page_id, slug = registration_page
    intro = '<h1>Title</h1><p class="lead">Mine</p><p>Body</p>'

    _save_intro(logged_in_admin, assembly_id, slug, intro, content_style="govuk")
    govuk = visitor.get(f"/register/{slug}").get_data(as_text=True)
    assert '<h1 class="govuk-heading-xl">Title</h1><p class="lead">Mine</p><p class="govuk-body">Body</p>' in govuk

    _save_intro(logged_in_admin, assembly_id, slug, intro, content_style="plain")
    plain = visitor.get(f"/register/{slug}").get_data(as_text=True)
    assert intro in plain


@pytest.mark.db_semantics
def test_a_page_from_before_content_styles_renders_unchanged(
    logged_in_admin, visitor, registration_page, postgres_session_factory
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
    assert "<h1>Title</h1><p>Body</p>" in visitor.get(f"/register/{slug}").get_data(as_text=True)


def test_public_page_styles_quotes_and_lines_but_leaves_tables_alone(logged_in_admin, visitor, registration_page):
    """Quotes and horizontal lines get GOV.UK classes; tables get none until layout or data is decided (Q6)."""
    assembly_id, _page_id, slug = registration_page
    table = '<table><tbody><tr><td><p><img src="/a.png" alt="A"></p></td><td><p>B</p></td></tr></tbody></table>'
    intro = f"<blockquote><p>Quoted</p></blockquote><hr><p><u>Under</u> <s>struck</s></p>{table}"

    _save_intro(logged_in_admin, assembly_id, slug, intro, content_style="govuk")

    public = visitor.get(f"/register/{slug}").get_data(as_text=True)
    assert '<blockquote class="govuk-inset-text"><p class="govuk-body">Quoted</p></blockquote>' in public
    assert '<hr class="govuk-section-break govuk-section-break--m govuk-section-break--visible">' in public
    assert '<p class="govuk-body"><u>Under</u> <s>struck</s></p>' in public
    assert '<table><tbody><tr><td><p class="govuk-body"><img src="/a.png" alt="A"></p></td>' in public

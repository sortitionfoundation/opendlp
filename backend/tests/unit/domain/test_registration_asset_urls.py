"""ABOUTME: Unit tests for rewriting registration asset URLs in HTML
ABOUTME: Covers image-by-id, image-by-slug and document-by-slug URLs, and what is left alone"""

import uuid

from opendlp.domain.registration_asset_urls import rewrite_asset_urls

OLD_IMAGE = uuid.UUID("11111111-1111-1111-1111-111111111111")
NEW_IMAGE = uuid.UUID("22222222-2222-2222-2222-222222222222")
SHA = "a" * 64


def test_image_by_id_is_rewritten():
    html = f'<img src="/register-assets/images/{OLD_IMAGE}.png" alt="x">'

    assert rewrite_asset_urls(html, {OLD_IMAGE: NEW_IMAGE}, {}) == (
        f'<img src="/register-assets/images/{NEW_IMAGE}.png" alt="x">'
    )


def test_image_by_id_in_upper_case_is_rewritten():
    html = f"/register-assets/images/{str(OLD_IMAGE).upper()}.png"

    assert rewrite_asset_urls(html, {OLD_IMAGE: NEW_IMAGE}, {}) == f"/register-assets/images/{NEW_IMAGE}.png"


def test_image_by_slug_is_rewritten():
    html = f'<img src="/register/climate/assets/{SHA}.png">'

    assert rewrite_asset_urls(html, {}, {"climate": "climate-copy"}) == (
        f'<img src="/register/climate-copy/assets/{SHA}.png">'
    )


def test_document_by_slug_is_rewritten_in_an_absolute_url():
    html = f'<a href="https://example.org/register/climate/documents/{SHA}.pdf">Info</a>'

    assert rewrite_asset_urls(html, {}, {"climate": "climate-copy"}) == (
        f'<a href="https://example.org/register/climate-copy/documents/{SHA}.pdf">Info</a>'
    )


def test_slug_that_is_a_prefix_of_another_is_not_confused():
    html = f"/register/climate-2/assets/{SHA}.png /register/climate/assets/{SHA}.png"

    result = rewrite_asset_urls(html, {}, {"climate": "new-one", "climate-2": "new-two"})

    assert result == f"/register/new-two/assets/{SHA}.png /register/new-one/assets/{SHA}.png"


def test_swapped_slugs_are_rewritten_once_not_chained():
    html = f"/register/a/assets/{SHA}.png /register/b/assets/{SHA}.png"

    assert (
        rewrite_asset_urls(html, {}, {"a": "b", "b": "a"})
        == f"/register/b/assets/{SHA}.png /register/a/assets/{SHA}.png"
    )


def test_unknown_ids_and_slugs_are_left_alone():
    other = uuid.uuid4()
    html = f"/register-assets/images/{other}.png /register/elsewhere/assets/{SHA}.png"

    assert rewrite_asset_urls(html, {OLD_IMAGE: NEW_IMAGE}, {"climate": "climate-copy"}) == html


def test_registration_page_link_itself_is_not_rewritten():
    """Only asset URLs are rewritten - a plain link to the original's page is the author's to keep or change."""
    html = '<a href="/register/climate">Register</a>'

    assert rewrite_asset_urls(html, {}, {"climate": "climate-copy"}) == html


def test_html_without_asset_urls_is_unchanged():
    html = "<p>{{ project_title }}</p>"

    assert rewrite_asset_urls(html, {OLD_IMAGE: NEW_IMAGE}, {"climate": "climate-copy"}) == html

"""ABOUTME: Rewrites registration image and document URLs embedded in HTML
ABOUTME: Points a copied page's HTML at the copy's own images and page slugs, not the original's"""

import re
import uuid
from collections.abc import Mapping

_IMAGE_BY_ID = re.compile(r"(/register-assets/images/)([0-9a-fA-F-]{36})(\.png)")
_ASSET_BY_SLUG = re.compile(r"(/register/)([^/\s\"'<>?#]+)(/(?:assets|documents)/)")


def rewrite_asset_urls(html: str, image_ids: Mapping[uuid.UUID, uuid.UUID], url_slugs: Mapping[str, str]) -> str:
    """Replace image IDs and page slugs in registration asset URLs, in one pass.

    Covers `/register-assets/images/<id>.png`, `/register/<slug>/assets/...` and
    `/register/<slug>/documents/...`. An ID or slug missing from its mapping is
    left alone. One pass means a new value is never itself rewritten again.
    """

    def _image(match: re.Match[str]) -> str:
        try:
            new_id = image_ids.get(uuid.UUID(match.group(2)))
        except ValueError:
            return match.group(0)
        return f"{match.group(1)}{new_id}{match.group(3)}" if new_id else match.group(0)

    def _slug(match: re.Match[str]) -> str:
        new_slug = url_slugs.get(match.group(2))
        return f"{match.group(1)}{new_slug}{match.group(3)}" if new_slug else match.group(0)

    return _ASSET_BY_SLUG.sub(_slug, _IMAGE_BY_ID.sub(_image, html))

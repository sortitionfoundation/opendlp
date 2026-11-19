"""ABOUTME: Where a request that changed a project's data goes back to
ABOUTME: The data source settings dialog, open over the project details page, which is where such requests come from"""

import uuid

from flask import url_for


def data_source_return_url(assembly_id: uuid.UUID) -> str:
    """The page to show after deleting data, removing a Google Sheet's settings, or abandoning an upload."""
    return url_for("backoffice.view_assembly", assembly_id=assembly_id, data_source=1)

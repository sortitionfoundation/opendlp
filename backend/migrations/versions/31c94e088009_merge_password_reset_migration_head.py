"""empty message

Revision ID: 31c94e088009
Revises: 23993534552f, a1b2c3d4e5f6
Create Date: 2025-12-12 09:26:07.711619

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "31c94e088009"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = ("23993534552f", "a1b2c3d4e5f6")  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

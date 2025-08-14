"""Remove username column and add first_name last_name columns

Revision ID: 36f822f76b45
Revises: 1aea6aa317b3
Create Date: 2025-08-14 23:05:01.401755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36f822f76b45'
down_revision: Union[str, Sequence[str], None] = '1aea6aa317b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Remove the unique constraint on username first
    op.drop_constraint("users_username_key", "users", type_="unique")
    
    # Drop the username column
    op.drop_column("users", "username")
    
    # Add first_name and last_name columns with empty string defaults
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=False, server_default=""))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=False, server_default=""))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the first_name and last_name columns
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    
    # Add back the username column
    op.add_column("users", sa.Column("username", sa.String(length=50), nullable=False))
    
    # Re-create the unique constraint on username
    op.create_unique_constraint("users_username_key", "users", ["username"])

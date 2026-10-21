"""empty message

Revision ID: ebb4b1e0fe00
Revises: 6254d7cdd6d7
Create Date: 2026-10-10 16:37:08.242476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebb4b1e0fe00'
down_revision: Union[str, Sequence[str], None] = '6254d7cdd6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

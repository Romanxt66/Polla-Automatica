"""seed competitions

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPETITIONS = [
    {"code": "BETPLAY", "name": "Liga BetPlay", "country": "Colombia"},
    {"code": "UCL", "name": "UEFA Champions League", "country": "Europa"},
    {"code": "PL", "name": "Premier League", "country": "Inglaterra"},
]


def upgrade() -> None:
    competitions = sa.table(
        "competitions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("country", sa.String),
    )
    op.bulk_insert(competitions, COMPETITIONS)


def downgrade() -> None:
    codes = [c["code"] for c in COMPETITIONS]
    op.execute(
        sa.text("DELETE FROM competitions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", value=codes, expanding=True)
        )
    )

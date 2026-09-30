from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # BETPLAY | UCL | PL
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(60), default=None)

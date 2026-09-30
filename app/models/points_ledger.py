from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PointsLedger(TimestampMixin, Base):
    """Un registro por predicción liquidada. `prediction_id` único garantiza
    que los puntos de una predicción se calculan una sola vez."""

    __tablename__ = "points_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    points: Mapped[int] = mapped_column(Integer)
    is_exact: Mapped[bool] = mapped_column(default=False)

"""Ranking provisional del grupo, calculado desde PointsLedger.

Criterio: más puntos, luego más marcadores exactos, luego username. Los empatados en puntos
y exactos comparten posición (1, 1, 3). Cuando B fusione `services/leaderboard.py` (B5),
este módulo se reemplaza por el suyo o se elimina.
"""

from sqlalchemy import Integer, case, func, select
from sqlalchemy.orm import Session

from app.models import GroupMember, PointsLedger, User
from app.schemas.ranking import RankingEntry


def get_group_ranking(db: Session, group_id: int) -> list[RankingEntry]:
    points = func.coalesce(func.sum(PointsLedger.points), 0)
    exact = func.coalesce(func.sum(case((PointsLedger.is_exact, 1), else_=0)), 0).cast(Integer)
    rows = db.execute(
        select(User.id, User.username, points, exact, func.count(PointsLedger.id))
        .select_from(GroupMember)
        .join(User, User.id == GroupMember.user_id)
        .outerjoin(
            PointsLedger,
            (PointsLedger.user_id == GroupMember.user_id)
            & (PointsLedger.group_id == GroupMember.group_id),
        )
        .where(GroupMember.group_id == group_id)
        .group_by(User.id, User.username)
        .order_by(points.desc(), exact.desc(), User.username)
    ).all()

    entries: list[RankingEntry] = []
    for i, (user_id, username, pts, hits, scored) in enumerate(rows, start=1):
        tied = entries and (entries[-1].points, entries[-1].exact_hits) == (pts, hits)
        entries.append(
            RankingEntry(
                rank=entries[-1].rank if tied else i,
                user_id=user_id,
                username=username,
                points=pts,
                exact_hits=hits,
                scored_predictions=scored,
            )
        )
    return entries

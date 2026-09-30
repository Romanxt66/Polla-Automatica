from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Competition
from app.schemas.competition import CompetitionOut

router = APIRouter(prefix="/competitions", tags=["competitions"])


@router.get("", response_model=list[CompetitionOut])
def list_competitions(db: DbSession, _: CurrentUser) -> list[Competition]:
    return list(db.scalars(select(Competition).order_by(Competition.id)))

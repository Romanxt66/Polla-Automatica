from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession
from app.models import Competition, Match, MatchStatus
from app.schemas.competition import MatchOut

router = APIRouter(prefix="/matches", tags=["matches"])


def _match_out(m: Match) -> MatchOut:
    return MatchOut(
        id=m.id,
        competition_code=m.competition.code,
        home_team=m.home_team,
        away_team=m.away_team,
        kickoff_at=m.kickoff_at,
        status=m.status,
        home_score=m.home_score,
        away_score=m.away_score,
    )


@router.get("", response_model=list[MatchOut])
def list_matches(
    db: DbSession,
    _: CurrentUser,
    competition: Annotated[str | None, Query(description="Código: BETPLAY, UCL, PL")] = None,
    status_: Annotated[MatchStatus | None, Query(alias="status")] = None,
    date_from: Annotated[datetime | None, Query(description="kickoff >= este valor")] = None,
    date_to: Annotated[datetime | None, Query(description="kickoff < este valor")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MatchOut]:
    query = select(Match).options(joinedload(Match.competition))
    if competition:
        query = query.join(Competition).where(Competition.code == competition.upper())
    if status_:
        query = query.where(Match.status == status_)
    if date_from:
        query = query.where(Match.kickoff_at >= date_from)
    if date_to:
        query = query.where(Match.kickoff_at < date_to)
    query = query.order_by(Match.kickoff_at, Match.id).limit(limit).offset(offset)
    return [_match_out(m) for m in db.scalars(query).unique()]


@router.get("/{match_id}", response_model=MatchOut)
def get_match(match_id: int, db: DbSession, _: CurrentUser) -> MatchOut:
    match = db.scalar(
        select(Match).where(Match.id == match_id).options(joinedload(Match.competition))
    )
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partido no encontrado")
    return _match_out(match)

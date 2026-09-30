from datetime import datetime

from pydantic import BaseModel

from app.models.match import MatchStatus


class CompetitionOut(BaseModel):
    code: str
    name: str
    country: str | None


class MatchOut(BaseModel):
    id: int
    competition_code: str
    home_team: str
    away_team: str
    kickoff_at: datetime
    status: MatchStatus
    home_score: int | None
    away_score: int | None

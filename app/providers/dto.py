from datetime import datetime

from pydantic import BaseModel

from app.models.match import MatchStatus


class FixtureDTO(BaseModel):
    external_id: str
    competition_code: str
    home_team: str
    away_team: str
    kickoff_at: datetime
    status: MatchStatus = MatchStatus.SCHEDULED
    home_score: int | None = None
    away_score: int | None = None


class MatchResultDTO(BaseModel):
    external_id: str
    status: MatchStatus
    home_score: int | None = None
    away_score: int | None = None

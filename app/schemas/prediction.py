from datetime import datetime

from pydantic import BaseModel, Field

from app.models.match import MatchStatus


class PredictionIn(BaseModel):
    home_score: int = Field(ge=0, le=99)
    away_score: int = Field(ge=0, le=99)


class PredictionOut(BaseModel):
    group_id: int
    match_id: int
    home_team: str
    away_team: str
    kickoff_at: datetime
    match_status: MatchStatus
    home_score: int
    away_score: int
    updated_at: datetime

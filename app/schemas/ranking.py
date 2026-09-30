from pydantic import BaseModel


class RankingEntry(BaseModel):
    rank: int
    user_id: int
    username: str
    points: int
    exact_hits: int
    scored_predictions: int

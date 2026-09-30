from datetime import UTC, datetime

from app.models import Match, MatchStatus


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite devuelve fechas sin zona


def is_open_for_predictions(match: Match, now: datetime | None = None) -> bool:
    """Se puede pronosticar solo si el partido no ha empezado."""
    now = now or datetime.now(UTC)
    return match.status == MatchStatus.SCHEDULED and _aware(match.kickoff_at) > now

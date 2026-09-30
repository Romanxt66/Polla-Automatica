import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Match, MatchStatus
from app.providers.base import ProviderError, ResultsProvider

logger = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite devuelve fechas sin zona


@dataclass
class SyncReport:
    created: int = 0
    updated: int = 0
    skipped: int = 0  # competiciones que no existen en la BD o fallos del proveedor


async def sync_fixtures(
    db: Session, provider: ResultsProvider, competition_codes: list[str] | None = None
) -> SyncReport:
    """Trae el calendario del proveedor y hace upsert en `matches` (clave: external_id).

    Es idempotente: ejecutarlo dos veces no duplica partidos. No pisa el resultado de un
    partido ya FINISHED (eso lo gestiona settle_matches).
    """
    report = SyncReport()
    competitions = {c.code: c for c in db.scalars(select(Competition))}
    codes = competition_codes if competition_codes is not None else sorted(competitions)

    for code in codes:
        competition = competitions.get(code)
        if competition is None:
            logger.warning("Competición %s no existe en la BD; se omite", code)
            report.skipped += 1
            continue
        try:
            fixtures = await provider.get_fixtures(code)
        except ProviderError:
            logger.exception("Fallo al traer fixtures de %s", code)
            report.skipped += 1
            continue

        existing = {
            m.external_id: m
            for m in db.scalars(
                select(Match).where(
                    Match.external_id.in_([f.external_id for f in fixtures])
                )
            )
        }
        for f in fixtures:
            match = existing.get(f.external_id)
            if match is None:
                db.add(
                    Match(
                        external_id=f.external_id,
                        competition_id=competition.id,
                        home_team=f.home_team,
                        away_team=f.away_team,
                        kickoff_at=f.kickoff_at,
                        status=f.status,
                    )
                )
                report.created += 1
                continue
            changed = False
            for attr in ("home_team", "away_team"):
                if getattr(match, attr) != getattr(f, attr):
                    setattr(match, attr, getattr(f, attr))
                    changed = True
            if _aware(match.kickoff_at) != _aware(f.kickoff_at):
                match.kickoff_at = f.kickoff_at
                changed = True
            if match.status != MatchStatus.FINISHED and match.status != f.status:
                match.status = f.status
                changed = True
            report.updated += changed
        db.commit()
    return report

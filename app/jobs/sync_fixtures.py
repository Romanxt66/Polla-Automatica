import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Match, MatchStatus
from app.providers.base import ProviderError, ResultsProvider, UnsupportedCompetition

logger = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite devuelve fechas sin zona


def _safe_status(f) -> MatchStatus:
    """Un partido solo se da por FINISHED aquí si el fixture trae el marcador; si no, se
    deja como estaba de LIVE/SCHEDULED para que settle_matches lo consulte y lo puntúe."""
    if f.status == MatchStatus.FINISHED and (f.home_score is None or f.away_score is None):
        return MatchStatus.LIVE
    return f.status


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
        except UnsupportedCompetition:
            logger.info("El proveedor no cubre %s; se omite", code)
            report.skipped += 1
            continue
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
                        status=_safe_status(f),
                        home_score=f.home_score,
                        away_score=f.away_score,
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
            if match.status != MatchStatus.FINISHED:
                new_status = _safe_status(f)
                if match.status != new_status:
                    match.status = new_status
                    changed = True
                if f.home_score is not None and f.away_score is not None:
                    if (match.home_score, match.away_score) != (f.home_score, f.away_score):
                        match.home_score, match.away_score = f.home_score, f.away_score
                        changed = True
            report.updated += changed
        db.commit()
    return report

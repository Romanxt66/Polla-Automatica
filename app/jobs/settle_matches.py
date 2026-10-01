import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Match, MatchStatus, PointsLedger, Prediction
from app.providers.base import ProviderError, ResultsProvider
from app.services.scoring import calculate_points, is_exact

logger = logging.getLogger(__name__)

# Ventana normal: partidos que empezaron hace menos de 4 h (duran ~2 h). Así no se gasta
# cuota de la API consultando partidos lejanos.
DEFAULT_WINDOW = timedelta(hours=4)


@dataclass
class SettleReport:
    polled: int = 0
    results_updated: int = 0
    points_created: int = 0


async def refresh_results(
    db: Session,
    provider: ResultsProvider,
    now: datetime | None = None,
    window: timedelta = DEFAULT_WINDOW,
) -> tuple[int, int]:
    """Consulta al proveedor los partidos ya iniciados (dentro de `window`) y aún sin cerrar.

    Devuelve (consultados, actualizados). Si no hay partidos candidatos no se hace
    ninguna llamada a la API; si los hay, se hace UNA sola consulta para todos.
    """
    now = now or datetime.now(UTC)
    candidates = db.scalars(
        select(Match).where(
            or_(
                Match.status.in_([MatchStatus.SCHEDULED, MatchStatus.LIVE]),
                # terminado pero sin marcador todavía: se vuelve a consultar
                and_(Match.status == MatchStatus.FINISHED, Match.home_score.is_(None)),
            ),
            Match.kickoff_at <= now,
            Match.kickoff_at > now - window,
        )
    ).all()
    if not candidates:
        return 0, 0
    try:
        # una sola consulta para todos los partidos (cuida la cuota de la API)
        results = await provider.get_match_results([m.external_id for m in candidates])
    except ProviderError:
        logger.exception("Fallo al consultar los resultados de %s partidos", len(candidates))
        return len(candidates), 0

    updated = 0
    for match in candidates:
        result = results.get(match.external_id)
        if result is None:
            logger.warning("El proveedor no devolvió el partido %s", match.external_id)
            continue
        changed = False
        if result.status != match.status:
            match.status = result.status
            changed = True
        if result.home_score is not None and result.away_score is not None:
            if (match.home_score, match.away_score) != (result.home_score, result.away_score):
                match.home_score, match.away_score = result.home_score, result.away_score
                changed = True
        updated += changed
    db.commit()
    return len(candidates), updated


def settle_finished(db: Session) -> int:
    """Crea los PointsLedger de los pronósticos de partidos FINISHED aún sin liquidar.

    Idempotente: solo toma pronósticos sin fila en points_ledger, y la restricción única
    sobre prediction_id impide duplicados incluso si dos procesos corren a la vez.
    """
    rows = db.execute(
        select(Prediction, Match)
        .join(Match, Match.id == Prediction.match_id)
        .outerjoin(PointsLedger, PointsLedger.prediction_id == Prediction.id)
        .where(
            Match.status == MatchStatus.FINISHED,
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
            PointsLedger.id.is_(None),
        )
    ).all()
    created = 0
    for prediction, match in rows:
        entry = PointsLedger(
            prediction_id=prediction.id,
            user_id=prediction.user_id,
            group_id=prediction.group_id,
            match_id=match.id,
            points=calculate_points(
                prediction.home_score, prediction.away_score, match.home_score, match.away_score
            ),
            is_exact=is_exact(
                prediction.home_score, prediction.away_score, match.home_score, match.away_score
            ),
        )
        try:
            with db.begin_nested():
                db.add(entry)
            created += 1
        except IntegrityError:  # otro proceso ya la liquidó
            continue
    db.commit()
    return created


async def settle_matches(
    db: Session,
    provider: ResultsProvider,
    now: datetime | None = None,
    window: timedelta = DEFAULT_WINDOW,
) -> SettleReport:
    """Actualiza resultados de partidos en juego y liquida los puntos de los terminados."""
    polled, updated = await refresh_results(db, provider, now=now, window=window)
    created = settle_finished(db)
    if created:
        logger.info("Puntos creados: %s", created)
    return SettleReport(polled=polled, results_updated=updated, points_created=created)

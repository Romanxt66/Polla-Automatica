EXACT = 5
OUTCOME_AND_DIFF = 3
OUTCOME = 1


def _outcome(home: int, away: int) -> int:
    """1 gana local, 0 empate, -1 gana visitante."""
    return (home > away) - (home < away)


def is_exact(pred_home: int, pred_away: int, real_home: int, real_away: int) -> bool:
    return (pred_home, pred_away) == (real_home, real_away)


def calculate_points(pred_home: int, pred_away: int, real_home: int, real_away: int) -> int:
    """Puntos de un pronóstico (función pura).

    - Marcador exacto: 5
    - Ganador/empate acertado y misma diferencia de goles: 3
    - Solo ganador/empate acertado: 1
    - Otro caso: 0
    """
    if is_exact(pred_home, pred_away, real_home, real_away):
        return EXACT
    if _outcome(pred_home, pred_away) != _outcome(real_home, real_away):
        return 0
    if pred_home - pred_away == real_home - real_away:
        return OUTCOME_AND_DIFF
    return OUTCOME

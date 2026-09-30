import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.models.match import MatchStatus
from app.providers.base import ProviderError
from app.providers.dto import FixtureDTO, MatchResultDTO

MATCH_DURATION = timedelta(hours=2)

_TEAMS: dict[str, list[tuple[str, str]]] = {
    "BETPLAY": [
        ("Atlético Nacional", "Millonarios"),
        ("Junior", "América de Cali"),
        ("Deportivo Cali", "Santa Fe"),
        ("Once Caldas", "Tolima"),
    ],
    "UCL": [
        ("Real Madrid", "Bayern Múnich"),
        ("Manchester City", "Inter"),
        ("PSG", "Barcelona"),
        ("Arsenal", "Juventus"),
    ],
    "PL": [
        ("Arsenal", "Chelsea"),
        ("Liverpool", "Everton"),
        ("Manchester City", "Manchester United"),
        ("Tottenham", "Newcastle"),
    ],
}
# Horas de inicio respecto a la medianoche UTC del día en que arrancó el proceso (el "ancla"):
# dos partidos ya jugados y dos por jugar, que irán pasando a LIVE y FINISHED con el tiempo.
_KICKOFF_OFFSETS_HOURS = [-48 + 15, -24 + 15, 24 + 15, 48 + 15]


_PROCESS_ANCHOR = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class FakeProvider:
    """Proveedor simulado para desarrollar y testear sin API real.

    El estado de cada partido se deduce de la hora actual: antes del inicio SCHEDULED,
    durante las 2 horas siguientes LIVE y después FINISHED con un marcador determinista
    (siempre el mismo para un external_id). `now` y `anchor` son inyectables para tests.
    """

    def __init__(
        self, now: Callable[[], datetime] | None = None, anchor: datetime | None = None
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._anchor = anchor or _PROCESS_ANCHOR

    def _schedule(self) -> dict[str, tuple[str, str, str, datetime]]:
        table = {}
        for code, pairs in _TEAMS.items():
            for i, ((home, away), offset) in enumerate(
                zip(pairs, _KICKOFF_OFFSETS_HOURS, strict=True)
            ):
                kickoff = self._anchor + timedelta(hours=offset)
                table[f"fake-{code}-{i}"] = (code, home, away, kickoff)
        return table

    @staticmethod
    def _final_score(external_id: str) -> tuple[int, int]:
        digest = hashlib.sha256(external_id.encode()).digest()
        return digest[0] % 4, digest[1] % 4

    def _status(self, kickoff: datetime) -> MatchStatus:
        now = self._now()
        if now < kickoff:
            return MatchStatus.SCHEDULED
        if now < kickoff + MATCH_DURATION:
            return MatchStatus.LIVE
        return MatchStatus.FINISHED

    async def get_fixtures(self, competition_code: str) -> list[FixtureDTO]:
        if competition_code not in _TEAMS:
            raise ProviderError(f"Competición desconocida: {competition_code}")
        fixtures = []
        for ext_id, (code, home, away, kickoff) in sorted(self._schedule().items()):
            if code != competition_code:
                continue
            result = await self.get_match_result(ext_id)
            fixtures.append(
                FixtureDTO(
                    external_id=ext_id,
                    competition_code=code,
                    home_team=home,
                    away_team=away,
                    kickoff_at=kickoff,
                    status=result.status,
                    home_score=result.home_score,
                    away_score=result.away_score,
                )
            )
        return fixtures

    async def get_match_result(self, external_id: str) -> MatchResultDTO:
        entry = self._schedule().get(external_id)
        if entry is None:
            raise ProviderError(f"Partido desconocido: {external_id}")
        status = self._status(entry[3])
        if status == MatchStatus.SCHEDULED:
            return MatchResultDTO(external_id=external_id, status=status)
        if status == MatchStatus.LIVE:
            return MatchResultDTO(
                external_id=external_id, status=status, home_score=0, away_score=0
            )
        home, away = self._final_score(external_id)
        return MatchResultDTO(
            external_id=external_id, status=status, home_score=home, away_score=away
        )

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.models.match import MatchStatus
from app.providers.base import ProviderError, UnsupportedCompetition
from app.providers.dto import FixtureDTO, MatchResultDTO

logger = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"

# código interno -> código de competición en football-data.org (el plan gratis no incluye
# la Liga BetPlay, por eso no aparece aquí)
COMPETITION_CODES = {"PL": "PL", "UCL": "CL"}

# /matches?ids= admite varios ids; se parte en grupos para mantener la URL corta
MAX_IDS_PER_REQUEST = 20

_SCHEDULED = {"SCHEDULED", "TIMED"}
_LIVE = {"IN_PLAY", "PAUSED", "LIVE"}
_FINISHED = {"FINISHED", "AWARDED"}
_POSTPONED = {"POSTPONED", "SUSPENDED", "CANCELLED"}


def map_status(status: str) -> MatchStatus:
    if status in _FINISHED:
        return MatchStatus.FINISHED
    if status in _LIVE:
        return MatchStatus.LIVE
    if status in _POSTPONED:
        return MatchStatus.POSTPONED
    return MatchStatus.SCHEDULED  # SCHEDULED, TIMED y cualquier estado desconocido


def _scores(match: dict[str, Any], status: MatchStatus) -> tuple[int | None, int | None]:
    """Marcador a los 90 minutos: si hubo prórroga o penales, `regularTime` lo trae aparte
    porque `fullTime` incluye prórroga y penales."""
    if status == MatchStatus.SCHEDULED:
        return None, None
    score = match.get("score") or {}
    source = score.get("fullTime") or {}
    if status == MatchStatus.FINISHED:
        regular = score.get("regularTime") or {}
        if regular.get("home") is not None and regular.get("away") is not None:
            source = regular
    return source.get("home"), source.get("away")


class FootballDataProvider:
    """Implementa ResultsProvider sobre football-data.org v4 (plan gratis: 10 llamadas/min)."""

    def __init__(
        self,
        token: str,
        season: int | None = None,
        base_url: str = BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise ProviderError("Falta FOOTBALL_DATA_TOKEN para usar el proveedor football_data")
        self._season = season
        self._client = client or httpx.AsyncClient(
            base_url=base_url, headers={"X-Auth-Token": token}, timeout=15
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise ProviderError("football-data.org: límite de llamadas por minuto") from exc
            raise ProviderError(f"Error consultando football-data.org: {exc}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Error consultando football-data.org: {exc}") from exc
        remaining = response.headers.get("x-requests-available-minute")
        if remaining is not None:
            logger.info("football-data.org: quedan %s llamadas este minuto", remaining)
        return body

    @staticmethod
    def _parse_date(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

    @staticmethod
    def _to_result(match: dict[str, Any]) -> MatchResultDTO:
        status = map_status(match["status"])
        home, away = _scores(match, status)
        return MatchResultDTO(
            external_id=str(match["id"]), status=status, home_score=home, away_score=away
        )

    async def get_fixtures(self, competition_code: str) -> list[FixtureDTO]:
        code = COMPETITION_CODES.get(competition_code)
        if code is None:
            raise UnsupportedCompetition(
                f"football-data.org (plan gratis) no cubre {competition_code}"
            )
        params = {"season": self._season} if self._season else None
        body = await self._get(f"/competitions/{code}/matches", params)
        fixtures = []
        for match in body.get("matches", []):
            status = map_status(match["status"])
            home, away = _scores(match, status)
            fixtures.append(
                FixtureDTO(
                    external_id=str(match["id"]),
                    competition_code=competition_code,
                    home_team=match["homeTeam"].get("name") or "Por definir",
                    away_team=match["awayTeam"].get("name") or "Por definir",
                    kickoff_at=self._parse_date(match["utcDate"]),
                    status=status,
                    home_score=home,
                    away_score=away,
                )
            )
        return fixtures

    async def get_match_result(self, external_id: str) -> MatchResultDTO:
        return self._to_result(await self._get(f"/matches/{external_id}"))

    async def get_match_results(self, external_ids: list[str]) -> dict[str, MatchResultDTO]:
        results: dict[str, MatchResultDTO] = {}
        for start in range(0, len(external_ids), MAX_IDS_PER_REQUEST):
            chunk = external_ids[start : start + MAX_IDS_PER_REQUEST]
            try:
                body = await self._get("/matches", {"ids": ",".join(chunk)})
                for match in body.get("matches", []):
                    results[str(match["id"])] = self._to_result(match)
            except ProviderError:
                # si el filtro por ids no está disponible en el plan, se pide uno a uno
                logger.warning("Consulta por lote falló; se consulta partido por partido")
                for ext_id in chunk:
                    try:
                        results[ext_id] = await self.get_match_result(ext_id)
                    except ProviderError:
                        logger.exception("No se pudo consultar el partido %s", ext_id)
        return results

    async def aclose(self) -> None:
        await self._client.aclose()

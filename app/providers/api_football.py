import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.models.match import MatchStatus
from app.providers.base import ProviderError, UnsupportedCompetition
from app.providers.dto import FixtureDTO, MatchResultDTO

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"

# código interno -> id de liga en API-Football
LEAGUE_IDS = {"BETPLAY": 239, "UCL": 2, "PL": 39}

# API-Football admite hasta 20 ids por consulta en /fixtures?ids=1-2-3
MAX_IDS_PER_REQUEST = 20

_SCHEDULED = {"TBD", "NS"}
_LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}
_FINISHED = {"FT", "AET", "PEN"}
_POSTPONED = {"PST", "CANC", "ABD", "SUSP", "AWO", "WO"}


def map_status(short: str) -> MatchStatus:
    if short in _FINISHED:
        return MatchStatus.FINISHED
    if short in _LIVE:
        return MatchStatus.LIVE
    if short in _POSTPONED:
        return MatchStatus.POSTPONED
    return MatchStatus.SCHEDULED  # NS, TBD y cualquier estado desconocido


def default_season(code: str, today: datetime | None = None) -> int:
    """Europa: la temporada lleva el año en que empieza (desde julio). Colombia: año actual."""
    today = today or datetime.now(UTC)
    if code == "BETPLAY":
        return today.year
    return today.year if today.month >= 7 else today.year - 1


def _scores(item: dict[str, Any], status: MatchStatus) -> tuple[int | None, int | None]:
    """Marcador a los 90 minutos para partidos terminados (sin prórroga ni penales)."""
    if status == MatchStatus.SCHEDULED:
        return None, None
    source = item["goals"]
    if status == MatchStatus.FINISHED:
        fulltime = (item.get("score") or {}).get("fulltime") or {}
        if fulltime.get("home") is not None and fulltime.get("away") is not None:
            source = fulltime
    return source.get("home"), source.get("away")


class ApiFootballProvider:
    """Implementa ResultsProvider sobre API-Football v3 (api-sports.io).

    Ojo con la cuota del plan gratis: cada llamada cuenta, por eso las consultas por
    partido solo las hace settle_matches sobre partidos dentro de la ventana de juego.
    """

    def __init__(
        self,
        api_key: str,
        season: int | None = None,
        base_url: str = BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("Falta API_FOOTBALL_KEY para usar el proveedor api_football")
        self._season = season
        self._client = client or httpx.AsyncClient(
            base_url=base_url, headers={"x-apisports-key": api_key}, timeout=15
        )

    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Error consultando API-Football: {exc}") from exc
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            logger.info("API-Football: quedan %s llamadas hoy", remaining)
        if body.get("errors"):  # la API responde 200 incluso con errores (cuota, llave...)
            raise ProviderError(f"API-Football devolvió errores: {body['errors']}")
        return body.get("response", [])

    @staticmethod
    def _parse_date(value: str) -> datetime:
        return datetime.fromisoformat(value).astimezone(UTC)

    async def get_fixtures(self, competition_code: str) -> list[FixtureDTO]:
        league = LEAGUE_IDS.get(competition_code)
        if league is None:
            raise UnsupportedCompetition(f"Competición desconocida: {competition_code}")
        season = self._season or default_season(competition_code)
        items = await self._get("/fixtures", {"league": league, "season": season})
        fixtures = []
        for item in items:
            status = map_status(item["fixture"]["status"]["short"])
            home, away = _scores(item, status)
            fixtures.append(
                FixtureDTO(
                    external_id=str(item["fixture"]["id"]),
                    competition_code=competition_code,
                    home_team=item["teams"]["home"]["name"],
                    away_team=item["teams"]["away"]["name"],
                    kickoff_at=self._parse_date(item["fixture"]["date"]),
                    status=status,
                    home_score=home,
                    away_score=away,
                )
            )
        return fixtures

    @staticmethod
    def _to_result(item: dict[str, Any]) -> MatchResultDTO:
        status = map_status(item["fixture"]["status"]["short"])
        home, away = _scores(item, status)
        return MatchResultDTO(
            external_id=str(item["fixture"]["id"]),
            status=status,
            home_score=home,
            away_score=away,
        )

    async def get_match_result(self, external_id: str) -> MatchResultDTO:
        items = await self._get("/fixtures", {"id": external_id})
        if not items:
            raise ProviderError(f"Partido no encontrado en API-Football: {external_id}")
        return self._to_result(items[0])

    async def get_match_results(self, external_ids: list[str]) -> dict[str, MatchResultDTO]:
        """Una sola llamada por cada 20 partidos (en vez de una por partido)."""
        results: dict[str, MatchResultDTO] = {}
        for start in range(0, len(external_ids), MAX_IDS_PER_REQUEST):
            chunk = external_ids[start : start + MAX_IDS_PER_REQUEST]
            items = await self._get("/fixtures", {"ids": "-".join(chunk)})
            for item in items:
                result = self._to_result(item)
                results[result.external_id] = result
        return results

    async def aclose(self) -> None:
        await self._client.aclose()

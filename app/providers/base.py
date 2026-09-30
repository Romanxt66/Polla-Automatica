from typing import Protocol

from app.providers.dto import FixtureDTO, MatchResultDTO


class ResultsProvider(Protocol):
    """Contrato que implementan FakeProvider y ApiFootballProvider."""

    async def get_fixtures(self, competition_code: str) -> list[FixtureDTO]: ...

    async def get_match_result(self, external_id: str) -> MatchResultDTO: ...


class ProviderError(Exception):
    """Fallo al consultar al proveedor de resultados (red, cuota, id desconocido...)."""

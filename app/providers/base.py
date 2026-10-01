from typing import Protocol

from app.providers.dto import FixtureDTO, MatchResultDTO


class ResultsProvider(Protocol):
    """Contrato que implementan FakeProvider y ApiFootballProvider."""

    async def get_fixtures(self, competition_code: str) -> list[FixtureDTO]: ...

    async def get_match_result(self, external_id: str) -> MatchResultDTO: ...

    async def get_match_results(self, external_ids: list[str]) -> dict[str, MatchResultDTO]:
        """Varios partidos en una sola consulta (clave: external_id).

        Los ids que el proveedor no devuelva simplemente no aparecen en el resultado. Un fallo
        total o parcial de la consulta lanza ProviderError.
        """
        ...


class ProviderError(Exception):
    """Fallo al consultar al proveedor de resultados (red, cuota, id desconocido...)."""

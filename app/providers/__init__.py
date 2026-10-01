from app.core.config import settings
from app.providers.base import ProviderError, ResultsProvider


def get_provider() -> ResultsProvider:
    """Elige el proveedor según RESULTS_PROVIDER (fake | api_football | football_data)."""
    name = settings.results_provider.lower()
    if name == "fake":
        from app.providers.fake import FakeProvider

        return FakeProvider()
    if name == "api_football":
        from app.providers.api_football import ApiFootballProvider

        return ApiFootballProvider(
            api_key=settings.api_football_key, season=settings.api_football_season
        )
    if name == "football_data":
        from app.providers.football_data import FootballDataProvider

        return FootballDataProvider(
            token=settings.football_data_token, season=settings.football_data_season
        )
    raise ProviderError(f"RESULTS_PROVIDER desconocido: {settings.results_provider}")

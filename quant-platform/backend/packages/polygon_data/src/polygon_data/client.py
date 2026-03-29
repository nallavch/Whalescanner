from collections.abc import Iterable

from core_models.market import AggregateBar


class PolygonAggregatesClient:
    """Polygon aggregate bars access layer (historical + live placeholders)."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch_historical(self, symbol: str, timespan: str = "minute") -> list[AggregateBar]:
        _ = (symbol, timespan)
        return []

    def stream_live(self, symbols: list[str]) -> Iterable[AggregateBar]:
        _ = symbols
        return []

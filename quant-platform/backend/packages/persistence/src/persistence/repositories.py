from core_models.market import AggregateBar


class MarketDataRepository:
    def save_bars(self, bars: list[AggregateBar]) -> None:
        _ = bars


class BacktestRepository:
    def save_result(self, result: dict[str, float]) -> str:
        _ = result
        return "phase1-result-id"

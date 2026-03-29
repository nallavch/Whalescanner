from core_models.market import AggregateBar
from strategies.base import Strategy


class BacktestEngine:
    def run(self, strategy: Strategy, bars: list[AggregateBar]) -> dict[str, float]:
        _ = strategy
        _ = bars
        return {"pnl": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}

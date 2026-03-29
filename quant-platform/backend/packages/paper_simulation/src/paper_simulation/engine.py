from core_models.market import AggregateBar
from strategies.base import Strategy


class PaperSimulationEngine:
    def on_bar(self, strategy: Strategy, bar: AggregateBar) -> None:
        _ = (strategy, bar)

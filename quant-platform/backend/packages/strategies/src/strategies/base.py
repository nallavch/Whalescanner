from abc import ABC, abstractmethod

from core_models.market import AggregateBar
from core_models.signals import StrategySignal


class Strategy(ABC):
    name: str

    @abstractmethod
    def on_bar(self, bar: AggregateBar) -> StrategySignal | None:
        raise NotImplementedError

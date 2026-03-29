from datetime import time

from core_models.market import AggregateBar
from core_models.signals import StrategySignal

from .base import Strategy


class MrVwapStrategy(Strategy):
    """Phase 1 placeholder for mean-reversion VWAP strategy.

    Planned inputs:
    - VWAP deviation bands
    - RSI filter
    - ATR-based stop logic
    - trading time-window constraints
    """

    name = "mr_vwap"

    def __init__(
        self,
        rsi_period: int = 14,
        atr_period: int = 14,
        open_time: time = time(9, 35),
        close_time: time = time(15, 50),
        vwap_deviation_threshold: float = 1.0,
    ) -> None:
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.open_time = open_time
        self.close_time = close_time
        self.vwap_deviation_threshold = vwap_deviation_threshold

    def on_bar(self, bar: AggregateBar) -> StrategySignal | None:
        _ = bar
        return None

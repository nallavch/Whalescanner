from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StrategySignal(BaseModel):
    strategy: str
    symbol: str
    timestamp: datetime
    side: Literal["buy", "sell", "flat"]
    confidence: float
    reason: str

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import datetime as dt

@dataclass
class TradeStats:
    count: int
    total_volume: int
    avg_size: float
    median_size: float
    buy_volume: int = 0
    sell_volume: int = 0

@dataclass
class SupportResistance:
    supports: List[float]
    resistances: List[float]
    last_close: Optional[float]
    closes: List[float]

@dataclass
class IntradayInfo:
    last_price: Optional[float] = None
    has_volume_spike: bool = False
    volume_spike_ratio: float = 0.0
    price_zscore: float = 0.0
    divergence: Optional[str] = None

@dataclass
class AbsorptionSummary:
    bullish_volume: int = 0
    bearish_volume: int = 0
    net_score: float = 0.0

@dataclass
class TradeSetup:
    label: str
    conviction_score: float
    explanation: str

@dataclass
class ScanResult:
    ticker: str
    date: str
    overall_stats: TradeStats
    block_stats: TradeStats
    clusters: List[Dict[str, Any]]
    support_resistance: SupportResistance
    trade_setup: TradeSetup
    intraday_info: IntradayInfo
    absorption_summary: AbsorptionSummary
    timeframe_bias: Dict[str, str]
    market_regime: str  # NEW: "ACCUMULATION", "DISTRIBUTION", "BULLISH", "BEARISH", "NEUTRAL"
    flow_aggregation: Dict[str, List[Dict[str, Any]]] # NEW: Aggregated flow data
    chart_signals: Dict[str, Any]
    intraday_bars: Dict[str, List[Dict[str, Any]]]

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime, timedelta

from flow_scanner import FlowScanner, get_cache_key, load_cache, save_cache  # your class-based scanner

app = FastAPI(title="Flow Scanner API")

# CORS for React dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def daterange(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


class DistanceCriteria(BaseModel):
    sma50: Optional[float] = Field(None, description="Max % distance from SMA50")
    sma150: Optional[float] = Field(None, description="Max % distance from SMA150")
    sma200: Optional[float] = Field(None, description="Max % distance from SMA200")


class ScreenerCriteria(BaseModel):
    require_sma50_above_200: bool = Field(False, description="SMA50 above SMA200")
    require_sma150_above_200: bool = Field(False, description="SMA150 above SMA200")
    min_relative_volume: Optional[float] = Field(
        None, description="Minimum relative volume vs 20-day average"
    )
    max_distance_percent: DistanceCriteria = Field(
        default_factory=DistanceCriteria,
        description="Max percentage distance from selected SMAs",
    )


class ScreenerRequest(BaseModel):
    tickers: List[str]
    source: str = Field("alpaca", pattern="^(alpaca|polygon)$")
    days_history: int = 250
    criteria: ScreenerCriteria = Field(default_factory=ScreenerCriteria)


@app.get("/api/scan/day")
def scan_day(
    ticker: str,
    date: Optional[str] = None,
    source: str = Query("alpaca", regex="^(alpaca|polygon)$"),
    block_size: int = 10000,
    trade_pages: int = Query(default=10),   # ← MUST BE HERE
    quote_pages: int = Query(default=10),   # ← MUST BE HERE
    plot: bool = False,   # 👈 NEW
    start_time: Optional[str] = None,  # "09:30"
    end_time: Optional[str] = None,    # "16:00"
):
    """
    Single-day deep scan:
    - whale clusters
    - intraday volume/mean reversion
    - support/resistance
    - trade setup
    """
    print(f"[Backend] Scanning {ticker} with trade_pages={trade_pages}")
    scanner = FlowScanner(source=source)
    result = scanner.run(
        ticker=ticker,
        date=date,
        block_size=block_size,
        trade_pages=trade_pages,      # ← MUST PASS HERE
        quote_pages=quote_pages,      # ← MUST PASS HERE
        days_history=90,
        verbose=False,
        plot=plot,   # 👈 pass through
        start_time=start_time,
        end_time=end_time,
    )
    return result

def decide_range_setup_label(
    block_buy: float,
    block_sell: float,
    tf_bias: dict,
) -> str:
    """
    Simple, intuitive rule for the Range Summary table:

    - LONG       : whales clearly net buyers AND 1H/4H bias up
    - SHORT      : whales clearly net sellers AND 1H/4H bias down
    - LONG_BIAS  : whales net buyers but trend not clearly up
    - SHORT_BIAS : whales net sellers but trend not clearly down
    - NEUTRAL    : flows balanced or inconclusive
    """

    gross = block_buy + block_sell
    if gross <= 0:
        return "NEUTRAL"

    # how dominant is one side?
    net_ratio = (block_buy - block_sell) / gross  # +1 = all buy, -1 = all sell

    bias_4h = (tf_bias or {}).get("4h")
    bias_1h = (tf_bias or {}).get("1h")
    up_trend = bias_4h == "up" or bias_1h == "up"
    down_trend = bias_4h == "down" or bias_1h == "down"

    # thresholds – you can tune these
    STRONG = 0.30   # 30% net dominance
    WEAK   = 0.10   # 10% net dominance

    # Strong alignment: big net flow + trend in same direction
    if net_ratio >= STRONG and up_trend:
        return "LONG"
    if net_ratio <= -STRONG and down_trend:
        return "SHORT"

    # Weak alignment: net flow but trend not clearly aligned
    if net_ratio >= WEAK:
        return "LONG_BIAS"
    if net_ratio <= -WEAK:
        return "SHORT_BIAS"

    return "NEUTRAL"


@app.get("/api/scan/range")
def scan_range(
    ticker: str,
    start_date: str,
    end_date: str,
    source: str = Query("alpaca", regex="^(alpaca|polygon)$"),
    block_size: int = 10000,
):
    """
    Multi-day overview.
    Returns per-day summaries (no heavy intraday details for each day).
    """
    scanner = FlowScanner(source=source)

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    day_summaries: List[dict] = []

    for d in daterange(start, end):
        date_str = d.strftime("%Y-%m-%d")
        try:
            res = scanner.run(
                ticker=ticker,
                date=date_str,
                block_size=block_size,
                trade_pages=10,
                quote_pages=10,
                days_history=30,
                verbose=False,
                plot=False,
            )
        except Exception as e:
            # Skip days with no data (weekends, holidays)
            continue

        overall = res["overall_stats"]
        block = res["block_stats"]
        sr = res["support_resistance"]
        setup = res["trade_setup"]
        intra = res["intraday_info"]

        # --- NEW: block buy/sell info ---
        block_buy = block.get("buy_volume", 0) or 0
        block_sell = block.get("sell_volume", 0) or 0
        block_total = block.get("total_volume", 0) or 0
        if block_total:
            block_buy_pct = block_buy * 100.0 / block_total
            block_sell_pct = block_sell * 100.0 / block_total
        else:
            block_buy_pct = 0.0
            block_sell_pct = 0.0

        block_net = block_buy - block_sell
        tf_bias = res.get("timeframe_bias") or {}
        range_label = decide_range_setup_label(block_buy, block_sell, tf_bias)


        day_summaries.append({
            "date": date_str,
            "total_volume": overall["total_volume"],
            "block_volume": block["total_volume"],
            "block_pct": (
                100 * block["total_volume"] / overall["total_volume"]
                if overall["total_volume"] else 0
            ),
            # --- NEW FIELDS EXPOSED TO FRONTEND ---
            "block_buy_volume": block_buy,
            "block_sell_volume": block_sell,
            "block_buy_pct": block_buy_pct,
            "block_sell_pct": block_sell_pct,
            "block_net_volume": block_net,
            
           # "setup_label": setup["label"],
           "setup_label": range_label,
            "has_volume_spike": intra.get("has_volume_spike"),
            "price_zscore": intra.get("price_zscore"),
            "last_close": sr.get("last_close"),
            "supports": sr.get("supports"),
            "resistances": sr.get("resistances"),
        })

    return {
        "ticker": ticker.upper(),
        "source": source,
        "start_date": start_date,
        "end_date": end_date,
        "days": day_summaries,
    }


def _compute_sma(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _compute_relative_volume(volumes: List[float], window: int = 20) -> Optional[float]:
    if len(volumes) < window or window <= 0:
        return None
    recent = volumes[-1]
    base = volumes[-window:]
    avg = sum(base) / len(base)
    if avg == 0:
        return None
    return recent / avg


def _distance_pct(close: Optional[float], sma: Optional[float]) -> Optional[float]:
    if close is None or sma is None or sma == 0:
        return None
    return abs(close - sma) * 100.0 / sma


@app.post("/api/scan/screener")
def screen_watchlist(req: ScreenerRequest):
    """Lightweight screener that tags tickers for a watchlist based on SMA/volume filters."""

    scanner = FlowScanner(source=req.source)
    provider = scanner.provider

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=req.days_history)

    matches = []

    for raw_ticker in req.tickers:
        ticker = raw_ticker.strip().upper()
        if not ticker:
            continue

        hist_key = get_cache_key(
            "screener_daily",
            ticker=ticker,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            source=req.source,
        )

        daily_bars = load_cache(hist_key)
        if not daily_bars:
            daily_bars = provider.fetch_daily_bars(
                ticker,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                verbose=False,
            )
            if daily_bars:
                save_cache(hist_key, daily_bars)

        if not daily_bars:
            matches.append(
                {
                    "ticker": ticker,
                    "passed": False,
                    "reasons": ["No daily data available"],
                }
            )
            continue

        closes = [b.get("close") for b in daily_bars if b.get("close") is not None]
        volumes = [b.get("volume") for b in daily_bars if b.get("volume") is not None]

        close = closes[-1] if closes else None

        sma50 = _compute_sma(closes, 50)
        sma150 = _compute_sma(closes, 150)
        sma200 = _compute_sma(closes, 200)
        rel_vol = _compute_relative_volume(volumes)

        dist50 = _distance_pct(close, sma50)
        dist150 = _distance_pct(close, sma150)
        dist200 = _distance_pct(close, sma200)

        passed = True
        reasons: List[str] = []

        if req.criteria.require_sma50_above_200 and not (sma50 and sma200 and sma50 > sma200):
            passed = False
            reasons.append("SMA50 is not above SMA200")

        if req.criteria.require_sma150_above_200 and not (sma150 and sma200 and sma150 > sma200):
            passed = False
            reasons.append("SMA150 is not above SMA200")

        if req.criteria.min_relative_volume is not None:
            if rel_vol is None or rel_vol < req.criteria.min_relative_volume:
                passed = False
                reasons.append("Relative volume below threshold")

        dist_cfg = req.criteria.max_distance_percent
        if dist_cfg.sma50 is not None and (dist50 is None or dist50 > dist_cfg.sma50):
            passed = False
            reasons.append("Price too far from SMA50")

        if dist_cfg.sma150 is not None and (dist150 is None or dist150 > dist_cfg.sma150):
            passed = False
            reasons.append("Price too far from SMA150")

        if dist_cfg.sma200 is not None and (dist200 is None or dist200 > dist_cfg.sma200):
            passed = False
            reasons.append("Price too far from SMA200")

        matches.append(
            {
                "ticker": ticker,
                "close": close,
                "sma50": sma50,
                "sma150": sma150,
                "sma200": sma200,
                "relative_volume": rel_vol,
                "distance_pct": {"sma50": dist50, "sma150": dist150, "sma200": dist200},
                "passed": passed,
                "reasons": reasons,
            }
        )

    passed = [m for m in matches if m.get("passed")]
    return {
        "source": req.source,
        "criteria": req.criteria.model_dump(),
        "matches": matches,
        "passed": passed,
    }

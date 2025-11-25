from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime, timedelta

from flow_scanner import FlowScanner  # your class-based scanner

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

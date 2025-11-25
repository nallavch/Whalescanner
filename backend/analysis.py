import bisect
import datetime as dt
from typing import List, Dict, Any, Optional, Tuple
from models import TradeStats, SupportResistance

try:
    import pandas as pd
except Exception:
    pd = None

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

DARK_POOL_EXCHANGES = {59, 60, 62, 63, 64}
DARK_POOL_CONDITIONS = {12, 37, 14}
TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}

# ---------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division with default value."""
    return numerator / denominator if denominator != 0 else default

def ns_to_time_str(ns: int, tz: dt.timezone = dt.timezone.utc) -> str:
    """Convert nanoseconds to datetime string."""
    s = ns / 1_000_000_000
    return dt.datetime.fromtimestamp(s, tz=tz).strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------------------
# Analysis Logic
# ---------------------------------------------------------------------

def compute_timeframe_bias(
    bars: List[Dict[str, Any]],
    lookback: int = 20,
    threshold_pct: float = 0.003,
) -> Optional[str]:
    """Compute simple price bias: up/down/flat."""
    if not bars or len(bars) < 3:
        return None

    closes = [b["close"] for b in bars[-lookback:]]
    avg_close = sum(closes) / len(closes)
    last = closes[-1]
    
    diff = safe_divide(last - avg_close, avg_close)
    
    if diff > threshold_pct:
        return "up"
    if diff < -threshold_pct:
        return "down"
    return "flat"


def tag_dark_pool(trades: List[Dict[str, Any]]) -> None:
    """Tag trades as dark pool based on exchange/conditions."""
    for t in trades:
        exch = t.get("exchange")
        conds = t.get("conditions") or []
        
        is_dp = (
            exch in DARK_POOL_EXCHANGES or 
            (isinstance(conds, list) and any(c in DARK_POOL_CONDITIONS for c in conds))
        )
        t["_is_dark_pool"] = is_dp


def build_quote_index(quotes: List[Dict[str, Any]]) -> Tuple[List[int], List[Dict[str, Any]]]:
    """Build sorted quote index for fast lookups."""
    filtered = [(q["ts_ns"], q) for q in quotes if q.get("ts_ns") is not None]
    filtered.sort(key=lambda x: x[0])
    return [ts for ts, _ in filtered], [q for _, q in filtered]


def infer_trade_side(
    trade: Dict[str, Any], 
    quote_times: List[int], 
    quotes: List[Dict[str, Any]]
) -> Optional[str]:
    """Infer if trade was buy/sell based on nearest quote."""
    if not quote_times or not quotes:
        return None
        
    trade_ts = trade.get("ts_ns")
    price = trade.get("price")
    
    if trade_ts is None or price is None:
        return None
        
    idx = bisect.bisect_right(quote_times, trade_ts) - 1
    if idx < 0:
        return None
        
    q = quotes[idx]
    bid = q.get("bid_price")
    ask = q.get("ask_price")
    
    if bid is None or ask is None:
        return None
        
    spread = ask - bid
    if spread <= 0:
        spread = abs(spread) or 0.01
        
    epsilon = max(spread * 0.1, 0.01)
    
    if price >= ask - epsilon:
        return "buy"
    if price <= bid + epsilon:
        return "sell"
    return "neutral"


def annotate_trades_with_side(
    trades: List[Dict[str, Any]], 
    quotes: List[Dict[str, Any]], 
    verbose: bool = True
) -> None:
    """Add side detection to all trades."""
    if not quotes:
        if verbose:
            print("[INFO] No quotes; skipping side detection")
        for t in trades:
            t["_side"] = None
        return
        
    if verbose:
        print(f"[INFO] Building quote index from {len(quotes)} quotes...")
        
    q_times, qlist = build_quote_index(quotes)
    counts = {"buy": 0, "sell": 0, "neutral": 0, "none": 0}
    
    for t in trades:
        side = infer_trade_side(t, q_times, qlist)
        t["_side"] = side
        counts[side if side else "none"] += 1
        
    if verbose:
        print(f"[INFO] Side detection: {counts}")


def summarize_trades(trades: List[Dict[str, Any]]) -> TradeStats:
    """Calculate comprehensive trade statistics."""
    if not trades:
        return TradeStats(0, 0, 0.0, 0.0)
        
    sizes = [int(t.get("size") or 0) for t in trades]
    total = sum(sizes)
    n = len(sizes)
    avg = total / n if n else 0
    
    sizes_sorted = sorted(sizes)
    mid = n // 2
    median = (
        (sizes_sorted[mid - 1] + sizes_sorted[mid]) / 2 
        if n % 2 == 0 
        else sizes_sorted[mid]
    )
    
    buy_vol = sum(t.get("size", 0) for t in trades if t.get("_side") == "buy")
    sell_vol = sum(t.get("size", 0) for t in trades if t.get("_side") == "sell")

    return TradeStats(n, total, avg, median, buy_vol, sell_vol)


def filter_block_trades(trades: List[Dict[str, Any]], min_size: int) -> List[Dict[str, Any]]:
    """Filter trades above minimum size threshold."""
    return [t for t in trades if (t.get("size") or 0) >= min_size]


def cluster_block_trades(
    block_trades: List[Dict[str, Any]],
    max_gap_ms: int = 250,
    max_price_diff: float = 0.02,
    require_same_side: bool = True,
) -> List[Dict[str, Any]]:
    """Cluster block trades into whale flows."""
    if not block_trades:
        return []
        
    enriched = sorted(
        [(t["ts_ns"], t) for t in block_trades if t.get("ts_ns")],
        key=lambda x: x[0]
    )
    
    clusters = []
    current = []
    start_ts = end_ts = last_ts = last_price = None
    cluster_side_hint = None

    def flush():
        nonlocal current, start_ts, end_ts, clusters
        if not current:
            return
            
        sizes = [int(t.get("size", 0)) for t in current]
        total = sum(sizes)
        
        prices = [(t.get("price"), t.get("size")) for t in current]
        ps = [(p, s) for p, s in prices if p is not None and s is not None]
        vwap = safe_divide(sum(p * s for p, s in ps), sum(s for _, s in ps))
        
        sides = [t.get("_side") for t in current if t.get("_side")]
        side = sides[0] if sides and all(s == sides[0] for s in sides) else "mixed"
        
        dp_vol = sum(t.get("size", 0) for t in current if t.get("_is_dark_pool"))
        
        clusters.append({
            "trades": current[:],
            "total_size": total,
            "vwap": vwap,
            "side": side,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "dark_pool_volume": dp_vol,
            "dark_pool_share": safe_divide(dp_vol, total),
        })
        current = []
        start_ts = end_ts = None

    for ts, t in enriched:
        price = t.get("price")
        side = t.get("_side")
        
        if not current:
            current = [t]
            start_ts = end_ts = last_ts = ts
            last_price = price
            cluster_side_hint = side
            continue
            
        dt_ms = (ts - last_ts) / 1_000_000.0 if last_ts else 0.0
        price_diff = abs(price - last_price) if (price and last_price) else 0.0
        same_side_ok = not require_same_side or not cluster_side_hint or not side or side == cluster_side_hint
        
        if dt_ms <= max_gap_ms and price_diff <= max_price_diff and same_side_ok:
            current.append(t)
            end_ts = ts
            last_ts = ts
            last_price = price
            if not cluster_side_hint and side:
                cluster_side_hint = side
        else:
            flush()
            current = [t]
            start_ts = end_ts = last_ts = ts
            last_price = price
            cluster_side_hint = side
            
    flush()
    
    for i, cl in enumerate(clusters, start=1):
        # Generate UID: BLK-{HHMM}-{001}
        # Use start_ts to get time
        ts_s = cl["start_ts"] / 1_000_000_000
        dt_obj = dt.datetime.fromtimestamp(ts_s, dt.timezone.utc) # internal ts is usually UTC or naive? 
        # Actually in data_provider we convert to ns, usually from UTC. 
        # Let's format as HHMM in UTC for consistency, or just use sequential ID.
        # User asked for UID.
        time_str = dt_obj.strftime("%H%M")
        cl["id"] = f"BLK-{time_str}-{i:03d}"
        
    return clusters


def aggregate_cluster_flow(
    clusters: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Aggregate block flow into time buckets (5m, 15m, 1h, 4h).
    Returns a dict with keys "5m", "15m", "1h", "4h".
    """
    if not clusters:
        return {tf: [] for tf in ["5m", "15m", "1h", "4h"]}
        
    # Helper to bucketize
    def bucketize(tf_minutes: int) -> List[Dict[str, Any]]:
        buckets = {}
        tf_ns = tf_minutes * 60 * 1_000_000_000
        
        for cl in clusters:
            ts = cl["end_ts"]
            # Floor timestamp to nearest bucket
            bucket_ts = (ts // tf_ns) * tf_ns
            
            if bucket_ts not in buckets:
                buckets[bucket_ts] = {
                    "ts_ns": bucket_ts,
                    "buy_vol": 0,
                    "sell_vol": 0,
                    "net_vol": 0,
                    "block_count": 0,
                    "total_vol": 0
                }
            
            b = buckets[bucket_ts]
            size = cl["total_size"]
            side = cl["side"]
            
            b["total_vol"] += size
            b["block_count"] += 1
            
            if side == "buy":
                b["buy_vol"] += size
                b["net_vol"] += size
            elif side == "sell":
                b["sell_vol"] += size
                b["net_vol"] -= size
                
        # Convert to list and sort
        result = sorted(buckets.values(), key=lambda x: x["ts_ns"])
        return result

    return {
        "5m": bucketize(5),
        "15m": bucketize(15),
        "1h": bucketize(60),
        "4h": bucketize(240),
    }


def compute_support_resistance(
    daily_bars: List[Dict[str, Any]],
    pivot_window: int = 3,
    max_levels: int = 5,
) -> SupportResistance:
    """Calculate support/resistance levels from daily bars."""
    if not daily_bars:
        return SupportResistance([], [], None, [])
        
    highs = [b["high"] for b in daily_bars]
    lows = [b["low"] for b in daily_bars]
    closes = [b["close"] for b in daily_bars]
    
    supports = []
    resistances = []
    
    for i in range(pivot_window, len(daily_bars) - pivot_window):
        low = lows[i]
        high = highs[i]
        window_lows = lows[i - pivot_window: i + pivot_window + 1]
        window_highs = highs[i - pivot_window: i + pivot_window + 1]
        
        if low == min(window_lows):
            supports.append(low)
        if high == max(window_highs):
            resistances.append(high)
            
    # Merge nearby levels (within 1%)
    def merge_levels(levels: List[float], threshold: float = 0.01) -> List[float]:
        if not levels:
            return []
        levels = sorted(levels)
        merged = []
        current_group = [levels[0]]
        
        for i in range(1, len(levels)):
            if (levels[i] - current_group[-1]) / current_group[-1] <= threshold:
                current_group.append(levels[i])
            else:
                merged.append(sum(current_group) / len(current_group))
                current_group = [levels[i]]
        merged.append(sum(current_group) / len(current_group))
        return merged

    supports = merge_levels(list(set(supports)))
    resistances = merge_levels(list(set(resistances)))
    
    # Filter to only keep levels close to current price (e.g., +/- 15%)
    last_close = closes[-1]
    supports = [s for s in supports if abs(s - last_close) / last_close < 0.15]
    resistances = [r for r in resistances if abs(r - last_close) / last_close < 0.15]

    supports = sorted(supports)[-max_levels:]
    resistances = sorted(resistances)[:max_levels]
    
    return SupportResistance(supports, resistances, closes[-1], closes)


def build_intraday_minute_bars(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build 1-minute OHLCV bars from trades."""
    if not trades:
        return []
        
    trades_sorted = sorted(trades, key=lambda t: t["ts_ns"])
    bars_map = {}
    
    for t in trades_sorted:
        ts_ns = t.get("ts_ns")
        price = t.get("price")
        size = int(t.get("size") or 0)
        side = t.get("_side")
        
        if ts_ns is None or price is None or size <= 0:
            continue
            
        dto = dt.datetime.fromtimestamp(ts_ns / 1_000_000_000, dt.timezone.utc)
        minute_dt = dto.replace(second=0, microsecond=0)
        key = minute_dt.isoformat()
        
        if key not in bars_map:
            bars_map[key] = {
                "minute": minute_dt,
                "ts_ns": ts_ns,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": size,
                "buy_vol": 0,
                "sell_vol": 0,
            }
        else:
            bar = bars_map[key]
            bar["close"] = price
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["volume"] += size
            
        if side == "buy":
            bars_map[key]["buy_vol"] += size
        elif side == "sell":
            bars_map[key]["sell_vol"] += size
            
    return sorted(bars_map.values(), key=lambda b: b["minute"])


def resample_intraday_bars(
    minute_bars: List[Dict[str, Any]],
    timeframe: str,
) -> List[Dict[str, Any]]:
    """Resample minute bars to higher timeframes."""
    if timeframe == "1m" or not minute_bars or pd is None:
        return minute_bars
        
    df = pd.DataFrame(minute_bars)
    
    if "ts_ns" in df.columns:
        df["dt"] = pd.to_datetime(df["ts_ns"], unit="ns", utc=True)
    else:
        return minute_bars
        
    df.set_index("dt", inplace=True)
    
    agg_spec = {}
    for col, fn in {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }.items():
        if col in df.columns:
            agg_spec[col] = fn
            
    if not agg_spec:
        return minute_bars
        
    if "ts_ns" in df.columns:
        agg_spec["ts_ns"] = "first"
        
    rule = f"{TF_MINUTES[timeframe]}min"
    agg = df.resample(rule).agg(agg_spec)
    agg.dropna(subset=[c for c in ["open", "high", "low", "close"] if c in agg.columns], inplace=True)
    
    out = []
    for idx, row in agg.iterrows():
        bar = {
            "ts_ns": int(row["ts_ns"]) if "ts_ns" in agg.columns else int(idx.value),
        }
        for col in ["open", "high", "low", "close", "volume"]:
            if col in agg.columns:
                bar[col] = float(row[col])
        out.append(bar)
        
    return out

def compute_vwap_bands(
    minute_bars: List[Dict[str, Any]],
    std_dev_multiplier: float = 2.0
) -> Dict[str, Any]:
    """Compute VWAP and standard deviation bands."""
    if not minute_bars:
        return {}
        
    cum_vol = 0.0
    cum_pv = 0.0
    squared_diffs = 0.0
    
    vwap_series = []
    upper_band = []
    lower_band = []
    
    for b in minute_bars:
        price = (b["high"] + b["low"] + b["close"]) / 3
        vol = b["volume"]
        
        cum_vol += vol
        cum_pv += price * vol
        
        vwap = cum_pv / cum_vol if cum_vol > 0 else price
        vwap_series.append(vwap)
        
        # Variance calculation (approximate running variance)
        # Var = E[X^2] - (E[X])^2 is unstable, using running sum of squared deviations from CURRENT vwap
        # Actually, standard VWAP bands use std dev of price from VWAP
        squared_diffs += (price - vwap) ** 2 * vol
        variance = squared_diffs / cum_vol if cum_vol > 0 else 0
        std_dev = variance ** 0.5
        
        upper_band.append(vwap + std_dev_multiplier * std_dev)
        lower_band.append(vwap - std_dev_multiplier * std_dev)
        
    return {
        "vwap": vwap_series,
        "upper": upper_band,
        "lower": lower_band,
        "current_vwap": vwap_series[-1] if vwap_series else None,
        "current_upper": upper_band[-1] if upper_band else None,
        "current_lower": lower_band[-1] if lower_band else None,
    }


def compute_rvol(
    minute_bars: List[Dict[str, Any]],
    daily_avg_vol: float,
) -> float:
    """
    Compute Relative Volume (RVOL) for the current session.
    RVOL = Cumulative Volume / (Daily Avg Vol * (Time Elapsed / Total Session Time))
    """
    if not minute_bars or daily_avg_vol <= 0:
        return 0.0
        
    current_cum_vol = sum(b["volume"] for b in minute_bars)
    
    # Estimate session progress
    # Assuming 6.5 hours trading day (390 mins)
    # We can count bars if they are 1-min bars
    mins_elapsed = len(minute_bars)
    total_session_mins = 390
    
    expected_vol_fraction = min(mins_elapsed / total_session_mins, 1.0)
    expected_vol = daily_avg_vol * expected_vol_fraction
    
    return safe_divide(current_cum_vol, expected_vol)


def detect_historical_divergences(
    minute_bars: List[Dict[str, Any]],
    lookback: int = 5
) -> List[Dict[str, Any]]:
    """
    Detect all divergence events in the intraday history.
    Returns a list of events with timestamp, price, and type.
    """
    if len(minute_bars) < lookback * 2:
        return []
        
    closes = [b["close"] for b in minute_bars]
    deltas = [b.get("buy_vol", 0) - b.get("sell_vol", 0) for b in minute_bars]
    
    # Cumulative Delta
    cum_delta = []
    curr = 0
    for d in deltas:
        curr += d
        cum_delta.append(curr)
        
    events = []
    
    # Iterate through history
    # We need at least lookback bars to compare
    for i in range(lookback, len(minute_bars)):
        # Current window end: i
        # Previous window end: i - lookback
        
        price_change = closes[i] - closes[i - lookback]
        delta_change = cum_delta[i] - cum_delta[i - lookback]
        
        event_type = None
        if price_change < 0 and delta_change > 0:
            event_type = "bullish_absorption"
        elif price_change > 0 and delta_change < 0:
            event_type = "bearish_absorption"
            
        if event_type:
            # Add event
            events.append({
                "ts_ns": minute_bars[i]["ts_ns"],
                "price": minute_bars[i]["close"],
                "type": event_type,
                "index": i
            })
            
            
    return events

def compute_market_regime(
    minute_bars: List[Dict[str, Any]],
    period_fast: int = 20,
    period_slow: int = 50,
) -> str:
    """
    Determine market regime:
    - BULLISH: Price > SMA50 & SMA20 > SMA50 & Price > SMA20
    - BEARISH: Price < SMA50 & SMA20 < SMA50 & Price < SMA20
    - ACCUMULATION: Price flat/choppy but CVD (Cumulative Volume Delta) rising
    - DISTRIBUTION: Price flat/choppy but CVD falling
    - NEUTRAL: No clear signal
    """
    if not minute_bars or len(minute_bars) < period_slow:
        return "NEUTRAL"
        
    closes = [b["close"] for b in minute_bars]
    
    # Simple Moving Averages
    def sma(data, period):
        return sum(data[-period:]) / period
        
    sma20 = sma(closes, period_fast)
    sma50 = sma(closes, period_slow)
    last_price = closes[-1]
    
    # Trend Check
    is_uptrend = last_price > sma20 > sma50
    is_downtrend = last_price < sma20 < sma50
    
    if is_uptrend:
        return "BULLISH"
    if is_downtrend:
        return "BEARISH"
        
    # If not strong trend, check for divergence (Accumulation/Distribution)
    # CVD Calculation
    deltas = [b.get("buy_vol", 0) - b.get("sell_vol", 0) for b in minute_bars]
    cvd = []
    curr = 0
    for d in deltas:
        curr += d
        cvd.append(curr)
        
    # Compare slope of Price vs CVD over last 30 bars
    lookback = 30
    if len(closes) < lookback:
        return "NEUTRAL"
        
    price_change = (closes[-1] - closes[-lookback]) / closes[-lookback]
    cvd_change = cvd[-1] - cvd[-lookback]
    
    # Accumulation: Price flat/down (-0.5% to +0.5%) AND CVD significantly UP
    if -0.005 <= price_change <= 0.005 and cvd_change > 0:
         # Check magnitude of CVD? For now just direction
         return "ACCUMULATION"
         
    # Distribution: Price flat/up AND CVD significantly DOWN
    if -0.005 <= price_change <= 0.005 and cvd_change < 0:
        return "DISTRIBUTION"
        
    return "NEUTRAL"

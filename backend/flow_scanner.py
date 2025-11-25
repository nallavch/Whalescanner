#!/usr/bin/env python3
"""
Optimized Multi-source institutional-flow & mean-reversion scanner
Refactored to use modular components: data_provider, analysis, models.
"""

import os
import time
import pickle
import hashlib
import datetime as dt
from typing import List, Dict, Any, Optional
from pathlib import Path

# Import from new modules
from models import (
    TradeStats, SupportResistance, IntradayInfo, AbsorptionSummary, 
    TradeSetup, ScanResult
)
from data_provider import AlpacaProvider, PolygonProvider
import analysis

# ---------------------------------------------------------------------
# Caching Logic
# ---------------------------------------------------------------------

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

def get_cache_key(prefix: str, **kwargs) -> str:
    """Generate a unique cache key based on arguments."""
    key_str = f"{prefix}:" + ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return hashlib.md5(key_str.encode()).hexdigest()

def load_cache(key: str) -> Optional[Any]:
    """Load data from cache if it exists and is not too old (e.g. 24h)."""
    p = CACHE_DIR / f"{key}.pkl"
    if p.exists():
        # Simple check: if file is older than 24h, ignore it? 
        # For historical data (past dates), it never changes, so we can keep it forever.
        # For "today", we might want shorter cache. 
        # For now, let's assume we cache everything and user clears cache if needed,
        # OR we rely on the date in the key. If date is today, maybe don't cache or short cache.
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None
    return None

def save_cache(key: str, data: Any) -> None:
    """Save data to cache."""
    p = CACHE_DIR / f"{key}.pkl"
    try:
        with open(p, "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        print(f"[Cache] Error saving {key}: {e}")

# ---------------------------------------------------------------------
# FlowScanner Class
# ---------------------------------------------------------------------

class FlowScanner:
    def __init__(self, source: str = "alpaca"):
        self.source = source
        if source == "polygon":
            self.provider = PolygonProvider()
        else:
            self.provider = AlpacaProvider()

    def run(
        self,
        ticker: str,
        date: Optional[str] = None,
        block_size: int = 10000,
        trade_pages: int = 10,
        quote_pages: int = 10,
        days_history: int = 90,
        verbose: bool = True,
        plot: bool = False,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main execution pipeline.
        """
        if not date:
            # Default to today (or yesterday if weekend? logic left to caller usually)
            date = dt.datetime.now().strftime("%Y-%m-%d")

        # 1. Fetch Daily Bars (History)
        # -----------------------------------------------------------------
        # We need history for Support/Resistance
        history_start = (dt.datetime.strptime(date, "%Y-%m-%d") - dt.timedelta(days=days_history)).strftime("%Y-%m-%d")
        
        # Cache key for history
        hist_key = get_cache_key("history", ticker=ticker, start=history_start, end=date, source=self.source)
        daily_bars = load_cache(hist_key)
        
        if not daily_bars:
            daily_bars = self.provider.fetch_daily_bars(ticker, history_start, date, verbose=verbose)
            if daily_bars:
                save_cache(hist_key, daily_bars)

        sr = analysis.compute_support_resistance(daily_bars)
        tf_bias_label = analysis.compute_timeframe_bias(daily_bars)
        
        # 2. Fetch Trades (Intraday)
        # -----------------------------------------------------------------
        # Cache key for trades
        trades_key = get_cache_key(
            "trades", 
            ticker=ticker, 
            date=date, 
            pages=trade_pages, 
            source=self.source,
            start_time=start_time,
            end_time=end_time
        )
        trades = load_cache(trades_key)
        
        if not trades:
            # Construct start/end ts if provided
            # FIX: Interpret inputs as America/New_York and convert to UTC
            s_ts = None
            e_ts = None
            
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                # Fallback for older python versions if needed, though 3.9+ is standard now
                from backports.zoneinfo import ZoneInfo

            ny_tz = ZoneInfo("America/New_York")

            if start_time:
                # Parse YYYY-MM-DD + HH:MM -> Naive
                dt_naive = dt.datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
                # Localize to NY
                dt_ny = dt_naive.replace(tzinfo=ny_tz)
                # Convert to UTC
                dt_utc = dt_ny.astimezone(dt.timezone.utc)
                s_ts = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            if end_time:
                dt_naive = dt.datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
                dt_ny = dt_naive.replace(tzinfo=ny_tz)
                dt_utc = dt_ny.astimezone(dt.timezone.utc)
                e_ts = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            trades = self.provider.fetch_trades(
                ticker, date, 
                max_pages=trade_pages, 
                limit=50000 if self.source == "polygon" else 10000,
                verbose=verbose,
                start_ts=s_ts,
                end_ts=e_ts
            )
            if trades:
                save_cache(trades_key, trades)

        analysis.tag_dark_pool(trades)

        # 3. Fetch Quotes (Intraday) - ONLY if we need side detection
        # -----------------------------------------------------------------
        # We need quotes to determine buy/sell side accurately
        quotes_key = get_cache_key(
            "quotes", 
            ticker=ticker, 
            date=date, 
            pages=quote_pages, 
            source=self.source,
            start_time=start_time,
            end_time=end_time
        )
        quotes = load_cache(quotes_key)
        
        if not quotes:
            # Re-use the same logic for quotes if needed, or just re-calculate
            # (Since we didn't store the computed s_ts/e_ts in a wider scope above, we repeat or we could have lifted it)
            # Let's just repeat the logic briefly or better yet, do it once at top of function?
            # Actually, let's just do it here to be safe and consistent with the block above.
            
            # NOTE: Ideally we should refactor this into a helper, but for now inline is fine.
            s_ts_q = None
            e_ts_q = None
            
            # We need the import again if we didn't import at top level, but we did inside the method above? 
            # No, python imports are module level. But let's just assume it's imported or re-import to be safe if scope is weird.
            # Actually, let's just use the same logic.
            
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                from backports.zoneinfo import ZoneInfo

            ny_tz = ZoneInfo("America/New_York")

            if start_time:
                dt_naive = dt.datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
                dt_ny = dt_naive.replace(tzinfo=ny_tz)
                dt_utc = dt_ny.astimezone(dt.timezone.utc)
                s_ts_q = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            if end_time:
                dt_naive = dt.datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
                dt_ny = dt_naive.replace(tzinfo=ny_tz)
                dt_utc = dt_ny.astimezone(dt.timezone.utc)
                e_ts_q = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            quotes = self.provider.fetch_quotes(
                ticker, date, 
                max_pages=quote_pages, 
                limit=50000 if self.source == "polygon" else 10000,
                verbose=verbose,
                start_ts=s_ts_q,
                end_ts=e_ts_q
            )
            if quotes:
                save_cache(quotes_key, quotes)

        # 4. Analysis
        # -----------------------------------------------------------------
        analysis.annotate_trades_with_side(trades, quotes, verbose=verbose)
        
        overall_stats = analysis.summarize_trades(trades)
        
        block_trades = analysis.filter_block_trades(trades, block_size)
        block_stats = analysis.summarize_trades(block_trades)
        
        clusters = analysis.cluster_block_trades(block_trades)
        
        # Intraday Bars
        minute_bars = analysis.build_intraday_minute_bars(trades)
        bars_5m = analysis.resample_intraday_bars(minute_bars, "5m")
        bars_15m = analysis.resample_intraday_bars(minute_bars, "15m")
        bars_1h = analysis.resample_intraday_bars(minute_bars, "1h")
        bars_4h = analysis.resample_intraday_bars(minute_bars, "4h")
        
        # Intraday Info (Last price, Z-score, etc)
        last_price = minute_bars[-1]["close"] if minute_bars else None
        
        # VWAP Bands
        vwap_info = analysis.compute_vwap_bands(minute_bars)
        
        # Enrich minute bars with VWAP data for charting
        if vwap_info and minute_bars:
            for i, bar in enumerate(minute_bars):
                bar["vwap"] = vwap_info["vwap"][i]
                bar["upper_band"] = vwap_info["upper"][i]
                bar["lower_band"] = vwap_info["lower"][i]
        
        # RVOL
        # Use 30-day avg volume from daily bars if available, else 0
        avg_daily_vol = 0.0
        if daily_bars:
             # simple average of last 10 days
             recent_daily = daily_bars[-10:]
             avg_daily_vol = sum(b["volume"] for b in recent_daily) / len(recent_daily)
             
        rvol = analysis.compute_rvol(minute_bars, avg_daily_vol)

        # Simple Volume Spike Detection
        has_volume_spike = False
        vol_spike_ratio = 0.0
        if len(minute_bars) > 35:
            recent_vol = sum(b["volume"] for b in minute_bars[-5:]) / 5
            hist_vol = sum(b["volume"] for b in minute_bars[-35:-5]) / 30
            vol_spike_ratio = analysis.safe_divide(recent_vol, hist_vol)
            if vol_spike_ratio > 3.0:
                has_volume_spike = True

        # Z-Score (Price deviation from VWAP)
        price_zscore = 0.0
        current_vwap = vwap_info.get("current_vwap")
        if current_vwap and last_price:
             # Estimate std dev from bands (band = vwap + 2*std) -> std = (band - vwap)/2
             upper = vwap_info.get("current_upper")
             if upper:
                 std_est = (upper - current_vwap) / 2.0
                 price_zscore = analysis.safe_divide(last_price - current_vwap, std_est)

        # Absorption (Delta Divergence)
        divergence_events = analysis.detect_historical_divergences(minute_bars)
        
        # Get the latest divergence for the summary
        latest_divergence = None
        if divergence_events:
            # Check if the last event was recent (within last 5 mins)
            last_event = divergence_events[-1]
            if last_event["index"] >= len(minute_bars) - 5:
                latest_divergence = last_event["type"]
        
        bullish_vol = overall_stats.buy_volume
        bearish_vol = overall_stats.sell_volume
        net_score = analysis.safe_divide(bullish_vol - bearish_vol, bullish_vol + bearish_vol)
        
        absorption = AbsorptionSummary(
            bullish_volume=bullish_vol,
            bearish_volume=bearish_vol,
            net_score=net_score
        )

        # Trade Setup Logic
        # -----------------------------------------------------------------
        setup_label = "NEUTRAL"
        conviction = 50.0
        explanation = "No clear signal."

        # Logic:
        # 1. Whale Flow: Net Block Flow
        block_net_ratio = analysis.safe_divide(
            block_stats.buy_volume - block_stats.sell_volume, 
            block_stats.total_volume
        )
        
        # 2. Trend: Timeframe Bias
        trend_score = 0
        if tf_bias_label == "up": trend_score = 1
        elif tf_bias_label == "down": trend_score = -1
        
        # 3. RVOL Boost
        rvol_boost = 0
        if rvol > 1.5: rvol_boost = 10
        if rvol > 3.0: rvol_boost = 20
        
        # 4. Divergence Boost
        div_score = 0
        if latest_divergence == "bullish_absorption": div_score = 15
        elif latest_divergence == "bearish_absorption": div_score = -15
        
        # Combine
        # Base score from flow
        score = 50 + (block_net_ratio * 30) # +/- 30
        
        # Add trend
        score += (trend_score * 10)
        
        # Add divergence
        score += div_score
        
        # Add RVOL (only boosts conviction, doesn't change direction much)
        if abs(score - 50) > 10:
            score += (rvol_boost if score > 50 else -rvol_boost)
            
        conviction = min(max(score, 0), 100)
        
        if conviction >= 65:
            setup_label = "LONG"
            explanation = f"Strong Buying Flow + Alignment. RVOL={rvol:.1f}x."
        elif conviction <= 35:
            setup_label = "SHORT"
            explanation = f"Strong Selling Flow + Alignment. RVOL={rvol:.1f}x."
        elif conviction >= 55:
            setup_label = "LONG_BIAS"
            explanation = "Mild Buying Flow."
        elif conviction <= 45:
            setup_label = "SHORT_BIAS"
            explanation = "Mild Selling Flow."
            
        if latest_divergence:
            explanation += f" Detected {latest_divergence.replace('_', ' ')}."

        trade_setup = TradeSetup(
            label=setup_label,
            conviction_score=conviction,
            explanation=explanation
        )
        
        intraday_info = IntradayInfo(
            last_price=last_price,
            has_volume_spike=has_volume_spike,
            volume_spike_ratio=vol_spike_ratio,
            price_zscore=price_zscore,
            divergence=latest_divergence
        )

        # 5. Return Result
        # -----------------------------------------------------------------
        # We return a dict to be compatible with JSON serialization for API
        # Filter divergence events to reduce noise
        filtered_divergences = []
        if divergence_events:
            for evt in divergence_events:
                # Only show divergences that match the setup direction
                if "LONG" in setup_label and evt["type"] == "bullish_absorption":
                    filtered_divergences.append(evt)
                elif "SHORT" in setup_label and evt["type"] == "bearish_absorption":
                    filtered_divergences.append(evt)
                # If neutral, maybe show none or only very recent ones?
                # For now, let's show none to be clean
        
        # 5. Market Regime
        market_regime = analysis.compute_market_regime(minute_bars)

        # 6. Map Divergences to Clusters (Fix for missing Absorption data)
        if divergence_events and clusters:
            # Create a map of minute -> event type
            # Round event ts to nearest minute or check range
            div_map = {}
            for evt in divergence_events:
                # evt["ts_ns"]
                # Simple approach: check if cluster overlaps with event time
                div_map[evt["ts_ns"]] = evt["type"]
            
            for cl in clusters:
                cl_start = cl["start_ts"]
                cl_end = cl["end_ts"]
                cl["absorption"] = None
                
                # Check if any divergence event happened within cluster time window (or close to it)
                # We can check if any event ts is between start and end
                for evt in divergence_events:
                    ets = evt["ts_ns"]
                    # Allow 1 minute buffer
                    buffer_ns = 60 * 1_000_000_000
                    if (cl_start - buffer_ns) <= ets <= (cl_end + buffer_ns):
                        cl["absorption"] = evt["type"]
                        break
        
        # 7. Aggregated Flow
        flow_aggregation = analysis.aggregate_cluster_flow(clusters)

        return {
            "ticker": ticker,
            "date": date,
            "overall_stats": overall_stats.__dict__,
            "block_stats": block_stats.__dict__,
            "clusters": clusters,
            "support_resistance": sr.__dict__,
            "trade_setup": trade_setup.__dict__,
            "intraday_info": intraday_info.__dict__,
            "absorption_summary": absorption.__dict__,
            "timeframe_bias": {"1h": tf_bias_label, "4h": tf_bias_label}, # Simplified for now
            "market_regime": market_regime,
            "flow_aggregation": flow_aggregation,
            "chart_signals": {
                "divergence": latest_divergence,
                "divergence_events": filtered_divergences
            },
            "intraday_bars": {
                "1m": minute_bars,
                "5m": bars_5m,
                "15m": bars_15m,
                "1h": bars_1h,
                "4h": bars_4h
            }
        }

if __name__ == "__main__":
    # Simple CLI test
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    args = parser.parse_args()
    
    scanner = FlowScanner()
    res = scanner.run(args.ticker)
    print(res["trade_setup"])



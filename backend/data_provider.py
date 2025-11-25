import os
import requests
import datetime as dt
from typing import List, Dict, Any, Optional, Protocol

# ---------------------------------------------------------------------
# Utility functions for Providers
# ---------------------------------------------------------------------

def iso_to_ns(iso_str: str) -> int:
    """Convert ISO string to nanoseconds."""
    dt_obj = dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt_obj.timestamp() * 1_000_000_000)

# ---------------------------------------------------------------------
# Data provider protocol & implementations
# ---------------------------------------------------------------------

class DataProviderBase(Protocol):
    """Protocol for data providers."""
    
    def fetch_trades(self, ticker: str, date: str, **kwargs) -> List[Dict[str, Any]]:
        ...

    def fetch_quotes(self, ticker: str, date: str, **kwargs) -> List[Dict[str, Any]]:
        ...

    def fetch_daily_bars(self, ticker: str, from_date: str, to_date: str, **kwargs) -> List[Dict[str, Any]]:
        ...


class PolygonProvider:
    """Polygon.io data provider."""
    
    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("POLYGON_API_KEY")
        if not key:
            # It's better to log a warning than crash if the user might switch to Alpaca
            print("[WARNING] POLYGON_API_KEY not set. Polygon provider will fail if used.")
        self.api_key = key

    def _paginate_v3(
        self, 
        path: str, 
        params: Dict[str, Any], 
        max_pages: int, 
        verbose: bool
    ) -> List[Dict[str, Any]]:
        """Paginate through Polygon v3 API."""
        if not self.api_key:
             raise RuntimeError("POLYGON_API_KEY not set")

        url: Optional[str] = f"{self.BASE_URL}{path}"
        params = dict(params or {})
        params["apiKey"] = self.api_key
        all_results = []
        
        for page in range(max_pages):
            if not url:
                break
                
            if verbose:
                print(f"[Polygon] Page {page+1}/{max_pages}")
                
            try:
                resp = requests.get(
                    url, 
                    params=params if page == 0 else None, 
                    timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
                
                results = data.get("results", []) or []
                if not results:
                    break
                    
                all_results.extend(results)
                url = data.get("next_url")
                params = None
                
                if verbose:
                    print(f"[Polygon] Retrieved {len(results)} records (total: {len(all_results)})")
                    
            except requests.RequestException as e:
                print(f"[Polygon] Request error: {e}")
                break
                
        return all_results

    def fetch_trades(
        self,
        ticker: str,
        date: str,
        max_pages: int = 3,
        limit: int = 50000,
        verbose: bool = True,
    ) -> List[Dict[str, Any]]:
        params = {
            "timestamp": date,
            "limit": limit,
            "sort": "sip_timestamp",
            "order": "asc",
        }
        raw = self._paginate_v3(f"/v3/trades/{ticker}", params, max_pages, verbose)
        
        trades = []
        for t in raw:
            ts = t.get("sip_timestamp") or t.get("participant_timestamp") or t.get("t")
            if ts is None:
                continue
            trades.append({
                "ts_ns": ts,
                "price": t.get("price") or t.get("p"),
                "size": t.get("size") or t.get("s"),
                "exchange": t.get("exchange") or t.get("x"),
                "conditions": t.get("conditions") or t.get("c") or [],
            })
        return trades

    def fetch_quotes(
        self,
        ticker: str,
        date: str,
        max_pages: int = 3,
        limit: int = 50000,
        verbose: bool = True,
    ) -> List[Dict[str, Any]]:
        params = {
            "timestamp": date,
            "limit": limit,
            "sort": "sip_timestamp",
            "order": "asc",
        }
        raw = self._paginate_v3(f"/v3/quotes/{ticker}", params, max_pages, verbose)
        
        quotes = []
        for q in raw:
            ts = q.get("sip_timestamp") or q.get("participant_timestamp") or q.get("t")
            if ts is None:
                continue
            quotes.append({
                "ts_ns": ts,
                "bid_price": q.get("bid_price"),
                "ask_price": q.get("ask_price"),
            })
        return quotes

    def fetch_daily_bars(
        self,
        ticker: str,
        from_date: str,
        to_date: str,
        verbose: bool = True,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
             raise RuntimeError("POLYGON_API_KEY not set")

        url = f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 5000,
            "apiKey": self.api_key,
        }
        
        if verbose:
            print(f"[Polygon] Fetching daily bars {from_date} → {to_date}")
            
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", []) or []
            
            bars = []
            for bar in results:
                bars.append({
                    "ts_ns": bar.get("t") * 1_000_000, # Polygon returns ms for aggs usually
                    "open": bar.get("o"),
                    "high": bar.get("h"),
                    "low": bar.get("l"),
                    "close": bar.get("c"),
                    "volume": bar.get("v"),
                })
            return bars
        except requests.RequestException as e:
            print(f"[Polygon] Error fetching daily bars: {e}")
            return []


class AlpacaProvider:
    """Alpaca data provider."""
    
    BASE_URL = "https://data.alpaca.markets"

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        key = api_key or os.environ.get("ALPACA_API_KEY")
        sec = api_secret or os.environ.get("ALPACA_API_SECRET")
        if not key or not sec:
            print("[WARNING] ALPACA_API_KEY/SECRET not set. Alpaca provider will fail if used.")
        self.api_key = key
        self.api_secret = sec

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        }
    
    def fetch_trades(
        self,
        ticker: str,
        date: str,
        max_pages: int = 3,
        limit: int = 10000,
        verbose: bool = True,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
             raise RuntimeError("ALPACA_API_KEY not set")

        # Fallback to full day if not provided
        if start_ts is None:
            start_ts = f"{date}T00:00:00Z"
        if end_ts is None:
            end_ts = f"{date}T23:59:59Z"

        url = f"{self.BASE_URL}/v2/stocks/{ticker}/trades"
        params = {"start": start_ts, "end": end_ts, "limit": limit}
        
        all_trades = []
        next_token = None
        
        if verbose:
            print(f"[Alpaca] Target: {max_pages} pages × {limit:,} = {max_pages * limit:,} max trades")
        
        for page in range(max_pages):
            p = dict(params)
            if next_token:
                p["page_token"] = next_token
                
            if verbose:
                print(f"[Alpaca] Fetching trades page {page+1}/{max_pages}...")
                
            try:
                resp = requests.get(url, headers=self._headers(), params=p, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                
                raw = data.get("trades", []) or []
                for t in raw:
                    all_trades.append({
                        "ts_ns": iso_to_ns(t["t"]),
                        "price": t.get("p"),
                        "size": t.get("s"),
                        "exchange": t.get("x"),
                        "conditions": t.get("c") or [],
                    })
                
                if verbose:
                    print(f"[Alpaca] Page {page+1}: got {len(raw):,} trades (total: {len(all_trades):,})")
                
                next_token = data.get("next_page_token")
                if not next_token:
                    if verbose:
                        print(f"[Alpaca] No more pages available (finished at page {page+1})")
                    break
            except requests.RequestException as e:
                print(f"[Alpaca] Error fetching trades: {e}")
                break
        
        if verbose:
            print(f"[Alpaca] ✅ Final count: {len(all_trades):,} trades")
                
        return all_trades

    def fetch_quotes(
        self,
        ticker: str,
        date: str,
        max_pages: int = 3,
        limit: int = 10000,
        verbose: bool = True,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
             raise RuntimeError("ALPACA_API_KEY not set")

        if start_ts is None:
            start_ts = f"{date}T00:00:00Z"
        if end_ts is None:
            end_ts = f"{date}T23:59:59Z"

        url = f"{self.BASE_URL}/v2/stocks/{ticker}/quotes"
        params = {"start": start_ts, "end": end_ts, "limit": limit}
        
        all_quotes = []
        next_token = None
        
        for page in range(max_pages):
            p = dict(params)
            if next_token:
                p["page_token"] = next_token
                
            if verbose:
                print(f"[Alpaca] Fetching quotes page {page+1}/{max_pages}")
                
            try:
                resp = requests.get(url, headers=self._headers(), params=p, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                
                raw = data.get("quotes", []) or []
                for q in raw:
                    all_quotes.append({
                        "ts_ns": iso_to_ns(q["t"]),
                        "bid_price": q.get("bp"),
                        "ask_price": q.get("ap"),
                    })
                
                next_token = data.get("next_page_token")
                if not next_token:
                    break
            except requests.RequestException as e:
                print(f"[Alpaca] Error fetching quotes: {e}")
                break
                
        return all_quotes

    def fetch_daily_bars(
        self,
        ticker: str,
        from_date: str,
        to_date: str,
        verbose: bool = True,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
             raise RuntimeError("ALPACA_API_KEY not set")

        start = f"{from_date}T00:00:00Z"
        end = f"{to_date}T23:59:59Z"
        url = f"{self.BASE_URL}/v2/stocks/{ticker}/bars"
        params = {"timeframe": "1Day", "start": start, "end": end, "limit": 1000}
        
        if verbose:
            print(f"[Alpaca] Fetching daily bars {from_date} → {to_date}")
            
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            raw = data.get("bars", []) or []
            bars = []
            for bar in raw:
                bars.append({
                    "ts_ns": iso_to_ns(bar["t"]),
                    "open": bar.get("o"),
                    "high": bar.get("h"),
                    "low": bar.get("l"),
                    "close": bar.get("c"),
                    "volume": bar.get("v"),
                })
            return bars
        except requests.RequestException as e:
            print(f"[Alpaca] Error fetching daily bars: {e}")
            return []

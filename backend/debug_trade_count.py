#!/usr/bin/env python3
"""
Debug script to test trade fetching with different page counts
"""
import os
import sys
from datetime import date

# Import your scanner
try:
    from flow_scanner import FlowScanner
except ImportError:
    print("ERROR: Cannot import flow_scanner.py")
    print("Make sure you're running this from the same directory")
    sys.exit(1)

def test_trade_fetching():
    """Test different page counts to see actual trade retrieval"""
    
    # Configuration
    TICKER = "AAPL"  # Use a very liquid stock
    DATE = "2024-11-18"  # Recent trading day
    SOURCE = "alpaca"  # or "polygon"
    
    print("=" * 80)
    print(f"TESTING TRADE FETCH: {TICKER} on {DATE} via {SOURCE}")
    print("=" * 80)
    
    # Check API keys
    if SOURCE == "alpaca":
        if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_API_SECRET"):
            print("❌ ALPACA_API_KEY or ALPACA_API_SECRET not set!")
            return
    elif SOURCE == "polygon":
        if not os.getenv("POLYGON_API_KEY"):
            print("❌ POLYGON_API_KEY not set!")
            return
    
    print("✅ API keys found\n")
    
    # Test different page counts
    test_cases = [
        {"pages": 1, "expected": "~10K (Alpaca) or ~50K (Polygon)"},
        {"pages": 3, "expected": "~30K (Alpaca) or ~150K (Polygon)"},
        {"pages": 10, "expected": "~100K (Alpaca) or ~500K (Polygon)"},
    ]
    
    for test in test_cases:
        pages = test["pages"]
        expected = test["expected"]
        
        print(f"\n{'─' * 80}")
        print(f"TEST: Fetching with trade_pages={pages}")
        print(f"Expected: {expected}")
        print(f"{'─' * 80}")
        
        try:
            scanner = FlowScanner(source=SOURCE)
            
            # Run scan with specific page count
            result = scanner.run(
                ticker=TICKER,
                date=DATE,
                trade_pages=pages,
                quote_pages=pages,
                verbose=True,
                block_size=15000,
            )
            
            trade_count = result["overall_stats"]["count"]
            print(f"\n✅ SUCCESS: Retrieved {trade_count:,} trades")
            
            # Check if we hit the limit
            if SOURCE == "alpaca" and trade_count == pages * 10000:
                print(f"⚠️  Exactly {pages * 10000:,} trades - might be hitting page limit")
            elif SOURCE == "polygon" and trade_count == pages * 50000:
                print(f"⚠️  Exactly {pages * 50000:,} trades - might be hitting page limit")
            else:
                print(f"✅ Good - not hitting exact page limit")
            
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("DIAGNOSIS:")
    print("=" * 80)
    print("""
    If you're seeing exactly 30,000 trades every time:
    
    1. Check your FastAPI/backend endpoint:
       - Does it accept 'trade_pages' parameter?
       - Is it passing it to scanner.run()?
    
    2. Check your backend logs:
       - Look for "[Alpaca] Fetching trades page X"
       - Should see multiple page fetches
    
    3. Quick fix in backend:
       
       @app.get("/api/scan/day")
       async def scan_day(
           ticker: str,
           date: str,
           source: str,
           block_size: int,
           trade_pages: int = 10,  # ← Add this
           quote_pages: int = 10,  # ← Add this
           plot: bool = False
       ):
           scanner = FlowScanner(source=source)
           result = scanner.run(
               ticker=ticker,
               date=date,
               block_size=block_size,
               trade_pages=trade_pages,    # ← Pass it here
               quote_pages=quote_pages,    # ← Pass it here
           )
           return result
    
    4. Restart your backend server after making changes!
    """)

if __name__ == "__main__":
    test_trade_fetching()
from backend.flow_scanner import FlowScanner

scanner = FlowScanner(source="alpaca")  # or "polygon"
result = scanner.run(
    ticker="HOOD",
    date="2025-11-14",
    block_size=10000,
    trade_pages=5,
    quote_pages=5,
    days_history=90,
    plot=True,        # True to show clusters + S/R plot
)

print(result["trade_setup"]["label"])
print(result["trade_setup"]["explanation"])

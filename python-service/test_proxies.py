import os
import sys

# Try to find scar directory
sys.path.append(os.getcwd())

from scar import proxies
import json

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]

for sym in symbols:
    print(f"\n--- Testing {sym} ---")
    s1, r1, v1 = proxies.detect_whale_withdrawal_proxy(sym)
    print(f"S1 Whale: {s1} | Reason: {r1} | Val: {v1}")
    
    s2, r2, v2 = proxies.detect_supply_drying_proxy(sym)
    print(f"S2 Supply: {s2} | Reason: {r2} | Val: {v2}")
    
    s3, r3, v3 = proxies.detect_price_stable(sym)
    print(f"S3 Stable: {s3} | Reason: {r3} | Val: {v3}")
    
    s4, r4, v4 = proxies.detect_negative_funding(sym)
    print(f"S4 Funding: {s4} | Reason: {r4} | Val: {v4}")
    
    s5, r5, v5 = proxies.detect_silence(sym)
    print(f"S5 Silence: {s5} | Reason: {r5} | Val: {v5}")

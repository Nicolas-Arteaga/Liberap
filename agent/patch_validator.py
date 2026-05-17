import sys

file_path = r'c:\Users\Nicolas\Desktop\Verge\Verge\agent\setup_validator.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace TP distance for LSE
content = content.replace(
    'pct_tp_floor = entry_f * float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))',
    'tp_dist_pct = float(profile.get("minTpDistancePct", getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))) if profile else float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))\n        pct_tp_floor = entry_f * tp_dist_pct'
)

# Replace SL distance for LSE
content = content.replace(
    'pct_floor = entry_f * float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))',
    'sl_dist_pct = float(profile.get("minSlDistancePct", getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))) if profile else float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))\n        pct_floor = entry_f * sl_dist_pct'
)

# Replace Slippage for LSE
content = content.replace(
    'max_slip = float(\n            getattr(\n                config,\n                "LSE_MAX_ENTRY_SLIPPAGE_PCT",\n                getattr(config, "MAX_ENTRY_SLIPPAGE_PCT", 0.002),\n            )\n        )',
    'max_slip = float(profile.get("lseMaxEntrySlippagePct", getattr(config, "LSE_MAX_ENTRY_SLIPPAGE_PCT", 0.015))) if profile else float(getattr(config, "LSE_MAX_ENTRY_SLIPPAGE_PCT", 0.015))'
)

# Nexus TP/SL multipliers
content = content.replace(
    'tp_dist = range_pct * config.TP_MULTIPLIER',
    'tp_dist = range_pct * (float(profile.get("tpMultiplier", config.TP_MULTIPLIER)) if profile else config.TP_MULTIPLIER)'
)
content = content.replace(
    'sl_dist = range_pct * config.SL_MULTIPLIER',
    'sl_dist = range_pct * (float(profile.get("slMultiplier", config.SL_MULTIPLIER)) if profile else config.SL_MULTIPLIER)'
)

# Nexus Post Pump
content = content.replace(
    'post_pump_threshold = float(getattr(config, "POST_PUMP_MA7_DISTANCE_PCT", 0.035))',
    'post_pump_threshold = float(profile.get("maxMa7DistancePct", getattr(config, "POST_PUMP_MA7_DISTANCE_PCT", 0.035)) / 100.0) if profile else float(getattr(config, "POST_PUMP_MA7_DISTANCE_PCT", 0.035))'
)

# Nexus Signal Age
content = content.replace(
    'max_nexus_age = float(getattr(config, "MAX_NEXUS_SIGNAL_AGE_SECONDS", 120.0))',
    'max_nexus_age = float(profile.get("maxNexusSignalAgeSeconds", getattr(config, "MAX_NEXUS_SIGNAL_AGE_SECONDS", 120.0))) if profile else float(getattr(config, "MAX_NEXUS_SIGNAL_AGE_SECONDS", 120.0))'
)

# Nexus Drift Pct
content = content.replace(
    'max_drift_pct = float(getattr(config, "NEXUS_MAX_PRICE_DRIFT_PCT", 0.025))',
    'max_drift_pct = float(profile.get("nexusMaxPriceDriftPct", getattr(config, "NEXUS_MAX_PRICE_DRIFT_PCT", 0.025))) if profile else float(getattr(config, "NEXUS_MAX_PRICE_DRIFT_PCT", 0.025))'
)

# Nexus Estimated Range
content = content.replace(
    'MIN_RANGE_PCT = float(getattr(config, "MIN_ESTIMATED_RANGE_PCT", 3.0))',
    'MIN_RANGE_PCT = float(profile.get("minEstimatedRangePct", getattr(config, "MIN_ESTIMATED_RANGE_PCT", 3.0))) if profile else float(getattr(config, "MIN_ESTIMATED_RANGE_PCT", 3.0))'
)

# Nexus Min RR
content = content.replace(
    'min_rr = float(getattr(config, "MIN_RR_NEXUS", getattr(config, "MIN_RR_DEFAULT", 1.5)))',
    'min_rr = float(profile.get("minRR", getattr(config, "MIN_RR_NEXUS", 1.5))) if profile else float(getattr(config, "MIN_RR_NEXUS", 1.5))'
)

# Nexus TP Distance Pct
content = content.replace(
    'pct_tp = cp * float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))',
    'tp_dist_pct = float(profile.get("minTpDistancePct", getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))) if profile else float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))\n    pct_tp = cp * tp_dist_pct'
)

# Nexus SL Distance Pct
content = content.replace(
    'pct_sl = cp * float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))',
    'sl_dist_pct = float(profile.get("minSlDistancePct", getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))) if profile else float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))\n    pct_sl = cp * sl_dist_pct'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done.')

"""
VOLUME PROFILE real — histograma de volumen por nivel de precio.

A diferencia del proxy que ya existe en nexus15/feature_engine.py (que le
asigna TODO el volumen de la vela con mayor volumen al precio de su cierre),
acá el volumen de CADA vela se reparte proporcionalmente entre todos los
bins de precio que toca su rango [low, high] — según cuánto se superpone
cada bin con ese rango. Así el POC (punto de control) refleja dónde
realmente se negoció más volumen, no cuál vela individual tuvo más volumen.
"""
import pandas as pd
from typing import List, Dict, Tuple

BIN_COUNT_DEFAULT = 60
HVN_RATIO = 0.7  # bin es "nodo de alto volumen" si tiene >= 70% del volumen del POC


def build_volume_profile(df: pd.DataFrame, bin_count: int = BIN_COUNT_DEFAULT) -> Tuple[List[Dict], float]:
    lows = df["low"].tolist()
    highs = df["high"].tolist()
    vols = df["volume"].tolist()

    price_min = min(lows)
    price_max = max(highs)
    if price_max <= price_min or bin_count <= 0:
        return [], price_min

    bin_size = (price_max - price_min) / bin_count
    bin_volumes = [0.0] * bin_count

    for low, high, vol in zip(lows, highs, vols):
        candle_range = high - low
        if candle_range <= 0:
            idx = min(max(int((high - price_min) / bin_size), 0), bin_count - 1)
            bin_volumes[idx] += vol
            continue

        first_bin = max(0, int((low - price_min) / bin_size))
        last_bin = min(bin_count - 1, int((high - price_min) / bin_size))
        for b in range(first_bin, last_bin + 1):
            bin_low = price_min + b * bin_size
            bin_high = bin_low + bin_size
            overlap = min(high, bin_high) - max(low, bin_low)
            if overlap > 0:
                bin_volumes[b] += vol * (overlap / candle_range)

    poc_idx = max(range(bin_count), key=lambda b: bin_volumes[b])
    poc_volume = bin_volumes[poc_idx]
    poc_price = price_min + (poc_idx + 0.5) * bin_size

    bins = []
    for b in range(bin_count):
        bin_low = price_min + b * bin_size
        bin_high = bin_low + bin_size
        vol = bin_volumes[b]
        bins.append({
            "price_low": round(bin_low, 8),
            "price_high": round(bin_high, 8),
            "volume": round(vol, 4),
            "is_poc": b == poc_idx,
            "is_hvn": bool(poc_volume > 0 and vol >= HVN_RATIO * poc_volume),
        })

    return bins, poc_price


def poc_distance_pct(zone_top: float, zone_bottom: float, bins: List[Dict]) -> Tuple[float, bool]:
    """
    Distancia (en %) entre el borde de una zona FVG y el bin de volumen alto
    (HVN) más cercano. 0% = el HVN se superpone directamente con el gap.
    """
    hvn_bins = [b for b in bins if b["is_hvn"]]
    if not hvn_bins:
        return 999.0, False

    ref_price = (zone_top + zone_bottom) / 2.0 or 1.0
    best_dist_pct = None
    overlapping = False

    for hb in hvn_bins:
        if hb["price_high"] >= zone_bottom and hb["price_low"] <= zone_top:
            overlapping = True
            best_dist_pct = 0.0
            break
        if hb["price_low"] > zone_top:
            dist = hb["price_low"] - zone_top
        else:
            dist = zone_bottom - hb["price_high"]
        dist_pct = abs(dist) / ref_price * 100.0
        if best_dist_pct is None or dist_pct < best_dist_pct:
            best_dist_pct = dist_pct

    return round(best_dist_pct if best_dist_pct is not None else 999.0, 4), overlapping

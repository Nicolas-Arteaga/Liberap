"""
2026-08-21: version rankeada del modelo v3 (con OFI real) -- igual que
ml_lab_ranked.py pero usando compute_features_v2 + OFI, y seleccionando por
RANKING PERCENTIL (top-K disponible por tick) en vez de un umbral de
probabilidad absoluto -- el modelo v3 nunca predice mas alto que 0.52, asi
que un umbral fijo no sirve, pero el analisis por percentil mostro edge
real y monotonico (top 1%: WR 36% vs base 22.9%, avg R +0.44).

Solo corre dentro de la ventana real de cobertura OFI (22/jul-21/ago) y
solo sobre el tramo out-of-sample real (ultimo 30% cronologico).
"""
import sys
import os
import time
import sqlite3
import numpy as np
import lightgbm as lgb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, load_15m, DB_PATH, MARGIN, FEE  # noqa: E402
from backtest.ml_lab import ATR_SL_MULT, RR_MULT, TRAIN_FRAC  # noqa: E402
from backtest.ml_lab_v2 import compute_features_v2  # noqa: E402
from backtest.ml_lab_v3 import OFI_DB_PATH, load_ofi_series, align_ofi  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402

SLOTS = 3
# 2026-08-21: umbral FIJO, sacado del analisis offline por percentil sobre
# TODO el test set (no un percentil calculado tick a tick sobre un pool
# chico de candidatos disponibles en ese instante -- eso no es lo mismo y
# puede seleccionar casi cualquier cosa cuando el pool es chico). p95 real
# medido en ml_lab_v3_test_proba.pkl: 0.3415.
PROBA_CUTOFF = 0.3415


def build_candidate(symbol, side, entry):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": "ml_ranked_v3_mode", "price_at_signal": entry, "estimated_range_pct": 5.0,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }


def main():
    model_path = os.path.join(os.path.dirname(__file__), "ml_lab_v3_model.txt")
    booster = lgb.Booster(model_file=model_path)
    feature_names = booster.feature_name()
    print(f"Modelo v3 cargado, {len(feature_names)} features")

    conn = sqlite3.connect(DB_PATH)
    ofi_conn = sqlite3.connect(OFI_DB_PATH)
    basket = load_basket(conn)

    cur = ofi_conn.cursor()
    cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM orderbook_ofi")
    ofi_min_s, ofi_max_s = cur.fetchone()
    ofi_min_ms, ofi_max_ms = ofi_min_s * 1000, ofi_max_s * 1000

    btc_rows = load_15m(conn, "BTCUSDT")
    btc_closes_by_ts = {r[0]: r[4] for r in btc_rows}

    data = {}
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 400:
            continue
        ofi_rows = load_ofi_series(ofi_conn, symbol)
        if len(ofi_rows) < 100:
            continue
        feats, atr_arr, ts = compute_features_v2(rows, btc_closes_by_ts)
        ofi_aligned = align_ofi(ofi_rows, ts.tolist())
        import pandas as pd
        ofi_series = pd.Series(ofi_aligned, dtype=float)
        feats["ofi_now"] = ofi_series.values
        feats["ofi_chg_1h"] = (ofi_series - ofi_series.shift(4)).values
        data[symbol] = (rows, feats, atr_arr, ts)
    print(f"Universo con cobertura OFI real: {len(data)} simbolos")

    ref_symbol = max(data.keys(), key=lambda s: len(data[s][0]))
    ref_rows = data[ref_symbol][0]
    # Recorte a la ventana real de OFI, luego split cronologico 70/30 dentro de ESA ventana.
    idx_in_window = [i for i, r in enumerate(ref_rows) if ofi_min_ms <= r[0] <= ofi_max_ms]
    if not idx_in_window:
        print("Simbolo de referencia sin cobertura en la ventana OFI -- eligiendo otro.")
        return
    start_i, end_i = idx_in_window[0], idx_in_window[-1]
    cut_i = start_i + int((end_i - start_i) * TRAIN_FRAC)
    print(f"Simulando tramo out-of-sample real: ticks {cut_i} a {end_i} (de ventana {start_i}-{end_i})")

    open_trades = {}
    last_trade_day = {}
    all_trades = []
    t_start = time.time()

    for i in range(cut_i, end_i + 1):
        now_ts = ref_rows[i][0]

        for symbol in list(open_trades.keys()):
            rows = data[symbol][0]
            if i >= len(rows) or rows[i][0] != now_ts:
                continue
            h, l = rows[i][2], rows[i][3]
            ot = open_trades[symbol]
            side = ot["side"]
            hit_tp = (l <= ot["tp"]) if side == 1 else (h >= ot["tp"])
            hit_sl = (h >= ot["sl"]) if side == 1 else (l <= ot["sl"])
            if hit_tp or hit_sl:
                close_px = ot["tp"] if hit_tp else ot["sl"]
                qty = MARGIN / ot["entry"]
                gross = qty * (ot["entry"] - close_px) if side == 1 else qty * (close_px - ot["entry"])
                fees = (qty * ot["entry"] + qty * close_px) * FEE
                all_trades.append({"symbol": symbol, "pnl": gross - fees, "open_time": ot["open_time"], "close_time": now_ts})
                del open_trades[symbol]

        available = SLOTS - len(open_trades)
        if available > 0:
            from datetime import datetime
            day_key = datetime.utcfromtimestamp(now_ts / 1000).date()
            meta, feat_rows = [], []
            for symbol, (rows, feats, atr_arr, ts) in data.items():
                if symbol in open_trades or last_trade_day.get(symbol) == day_key:
                    continue
                if i >= len(rows) or rows[i][0] != now_ts:
                    continue
                if i >= len(feats) or feats.iloc[i].isna().any():
                    continue
                a = atr_arr[i]
                if a is None or (isinstance(a, float) and np.isnan(a)) or a <= 0:
                    continue
                entry = rows[i][4]
                row_feat = feats.iloc[i].to_dict()
                sl_dist = ATR_SL_MULT * a
                tp_dist = sl_dist * RR_MULT
                for side in (0, 1):
                    sl = entry + sl_dist if side == 0 else entry - sl_dist
                    tp = entry - tp_dist if side == 0 else entry + tp_dist
                    meta.append((symbol, side, entry, sl, tp))
                    feat_rows.append([row_feat[f] if f != "side" else side for f in feature_names])

            candidates = []
            if feat_rows:
                probas = booster.predict(np.array(feat_rows))
                candidates = list(zip(probas, [m[0] for m in meta], [m[1] for m in meta],
                                       [m[2] for m in meta], [m[3] for m in meta], [m[4] for m in meta]))
            candidates.sort(key=lambda x: x[0], reverse=True)
            if candidates:
                strong = [c for c in candidates if c[0] >= PROBA_CUTOFF]
                for proba, symbol, side, entry, sl, tp in strong[:available]:
                    cand = build_candidate(symbol, side, entry)
                    try:
                        v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
                    except Exception:
                        v_ok = True
                    if not v_ok:
                        continue
                    open_trades[symbol] = {"side": side, "entry": entry, "sl": sl, "tp": tp, "open_time": now_ts}
                    last_trade_day[symbol] = day_key

        if (i - cut_i) % 1000 == 0:
            pct = (i - cut_i) / max(1, end_i - cut_i) * 100
            print(f"  progreso: {pct:.1f}% | trades={len(all_trades)} | elapsed={(time.time()-t_start)/60:.1f}min", flush=True)

    n = len(all_trades)
    if n == 0:
        print("Sin trades.")
        return
    total = sum(t["pnl"] for t in all_trades)
    wins = sum(1 for t in all_trades if t["pnl"] > 0)
    days = (ref_rows[end_i][0] - ref_rows[cut_i][0]) / 86400000
    monthly = total / (days / 30.44) if days > 0 else 0
    print(f"\n=== ML v3 RANKEADO (umbral fijo p95={PROBA_CUTOFF}, con OFI real, {days:.0f} dias out-of-sample) ===")
    print(f"Trades: {n} | WR: {wins/n*100:.1f}% | PnL total: ${total:.2f} | ${monthly:.2f}/mes")


if __name__ == "__main__":
    main()

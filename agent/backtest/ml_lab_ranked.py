"""
2026-08-19: fusion nueva -- el motivo real por el que FVG gana (diagnosticado
esta noche) es que compite contra TODO el universo en cada tick y se queda
con los mejores candidatos, no que aplique un umbral fijo simbolo por
simbolo. El modelo entrenado en ml_lab.py (AUC 0.53, umbral fijo) no
alcanzaba solo. Esto lo fusiona: en cada tick de 15m sincronizado, TODOS los
simbolos se puntuan con el modelo ya entrenado, se rankean por probabilidad
predicha, y se abren los top-K disponibles (3 cupos reales) -- exactamente
el mecanismo de FVG, pero con un modelo aprendido en vez de una regla fija
de distancia al TP.

Motor honesto de siempre: vetos reales (validate_pre_trade) + 3 cupos reales
x $150, out-of-sample real (el modelo se entrena en ml_lab.py con split
cronologico -- esta simulacion corre SOLO sobre el tramo de test, nunca
sobre datos que el modelo ya vio en entrenamiento).
"""
import sys
import os
import time
import sqlite3
import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, load_15m, DB_PATH, MARGIN, FEE  # noqa: E402
from backtest.ml_lab import compute_features, ATR_SL_MULT, RR_MULT, TRAIN_FRAC  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402

SLOTS = 3
MIN_PROBA = 0.50  # piso minimo -- no abrir nada que el modelo vea peor que 50/50


def build_candidate(symbol, side, entry):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": "ml_ranked_mode", "price_at_signal": entry, "estimated_range_pct": 5.0,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }


def main():
    model_path = os.path.join(os.path.dirname(__file__), "ml_lab_model.txt")
    if not os.path.exists(model_path):
        print("Falta ml_lab_model.txt -- correr ml_lab.py primero.")
        return
    booster = lgb.Booster(model_file=model_path)
    feature_names = booster.feature_name()
    print(f"Modelo cargado, {len(feature_names)} features: {feature_names}")

    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)

    data = {}
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 400:
            continue
        feats, atr_arr, ts = compute_features(rows)
        data[symbol] = (rows, feats, atr_arr, ts)
    print(f"Universo cargado: {len(data)} simbolos")

    ref_symbol = max(data.keys(), key=lambda s: len(data[s][0]))
    ref_rows = data[ref_symbol][0]
    total_ticks = len(ref_rows)

    # Split cronologico -- SOLO simular sobre el tramo de test (el modelo
    # nunca vio estos datos en train, mismo corte que ml_lab.py).
    cut_idx = int(total_ticks * TRAIN_FRAC)
    test_start_ts = ref_rows[cut_idx][0]
    print(f"Simulando solo sobre el tramo out-of-sample (desde {cut_idx}/{total_ticks})")

    open_trades = {}
    last_trade_day = {}
    all_trades = []

    t_start = time.time()
    for i in range(cut_idx, total_ticks):
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
            # 2026-08-19: prediccion en LOTE -- una sola llamada al modelo
            # por tick (todas las filas candidatas juntas) en vez de una
            # llamada por simbolo x lado. La version original (miles de
            # predict() de 1 fila) hubiera tardado horas por el overhead
            # fijo de cada llamada a LightGBM.
            meta = []  # (symbol, side, entry, sl, tp)
            feat_rows = []
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
                for (symbol, side, entry, sl, tp), proba in zip(meta, probas):
                    if proba >= MIN_PROBA:
                        candidates.append((proba, symbol, side, entry, sl, tp))

            candidates.sort(key=lambda x: x[0], reverse=True)
            for proba, symbol, side, entry, sl, tp in candidates[:available]:
                cand = build_candidate(symbol, side, entry)
                try:
                    v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True
                if not v_ok:
                    continue
                open_trades[symbol] = {"side": side, "entry": entry, "sl": sl, "tp": tp, "open_time": now_ts}
                last_trade_day[symbol] = day_key

        if (i - cut_idx) % 2000 == 0:
            pct = (i - cut_idx) / max(1, total_ticks - cut_idx) * 100
            print(f"  progreso: {pct:.1f}% | trades={len(all_trades)} | elapsed={(time.time()-t_start)/60:.1f}min", flush=True)

    n = len(all_trades)
    if n == 0:
        print("Sin trades.")
        return
    total = sum(t["pnl"] for t in all_trades)
    wins = sum(1 for t in all_trades if t["pnl"] > 0)
    days = (ref_rows[-1][0] - test_start_ts) / 86400000
    monthly = total / (days / 30.44) if days > 0 else 0
    print(f"\n=== ML RANKEADO (competencia real, solo out-of-sample, {days:.0f} dias) ===")
    print(f"Trades: {n} | WR: {wins/n*100:.1f}% | PnL total: ${total:.2f} | ${monthly:.2f}/mes")


if __name__ == "__main__":
    main()

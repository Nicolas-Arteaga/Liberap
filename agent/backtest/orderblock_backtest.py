"""
2026-08-21: backtest honesto del detector real de Order Block + Market
Structure Shift (python-service/orderblock/detector.py) -- concepto NUEVO,
distinto de todo lo probado esta semana (no es RSI/MA/ATR con parametros
distintos, es un evento de estructura de mercado real).

SL estructural (no ATR generico): mas alla del propio Order Block --
invalidar el OB invalida la operacion, es la logica real de la tecnica, no
un multiplo arbitrario. TP: reusa el mismo TP de liquidez real que ya se
probo y dio estable en level_sweep_liquidity_tp.py (nivel de liquidez con
deteccion de impulso desproporcionado + haircut).

Motor honesto de siempre: vetos reales + 3 cupos x $150, periodo real
completo, split cronologico para chequear estabilidad entre mitades.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python-service"))
from backtest.strategy_lab import (  # noqa: E402
    load_basket, load_15m, DB_PATH, MARGIN, FEE, _apply_capital_sim, evaluate,
)
from backtest.level_sweep_liquidity_tp import liquidity_tp  # noqa: E402
from backtest.level_sweep_poc_filter import hvn_bins, dist_to_nearest_hvn_pct, VP_WINDOW, MAX_POC_DIST_PCT  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402
from orderblock.detector import detect_order_block_signals  # noqa: E402

SL_BUFFER_RATIO = 0.15  # mismo criterio que FVG real: SL un poco mas alla del borde de invalidacion


def build_candidate(symbol, side, entry):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": "orderblock_mode", "price_at_signal": entry, "estimated_range_pct": 5.0,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }


def backtest_orderblock(conn, basket, apply_vetos=True, use_liquidity_tp=True, sl_mode="structural",
                         side_filter=None, apply_poc_filter=False, vols_cache=None):
    all_trades = []
    n_signals = 0
    n_poc_pass = 0
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 400:
            continue
        opens = [r[1] for r in rows]
        highs = [r[2] for r in rows]
        lows = [r[3] for r in rows]
        closes = [r[4] for r in rows]
        vols = [r[5] for r in rows]
        open_times = [r[0] for r in rows]

        signals = detect_order_block_signals(opens, highs, lows, closes, open_times)
        n_signals += len(signals)

        # Simular cada señal de forma independiente hacia adelante (sin
        # solaparse con otra señal del MISMO simbolo -- el capital sim
        # global despues aplica el limite real de 3 cupos entre simbolos).
        occupied_until = -1
        for sig in signals:
            i = sig["entry_idx"]
            if i <= occupied_until:
                continue
            side = 0 if sig["direction"] == "bullish" else 1
            if side_filter is not None and side != side_filter:
                continue
            entry = sig["entry_price"]
            ob_top, ob_bottom = sig["ob_top"], sig["ob_bottom"]
            gap_size = ob_top - ob_bottom
            if gap_size <= 0:
                continue

            if apply_poc_filter:
                start = max(0, i - VP_WINDOW)
                hvns, _ = hvn_bins(highs[start:i + 1], lows[start:i + 1], vols[start:i + 1])
                dist_pct = dist_to_nearest_hvn_pct(entry, hvns)
                if dist_pct > MAX_POC_DIST_PCT:
                    continue
                n_poc_pass += 1

            if sl_mode == "structural":
                sl = (ob_bottom - gap_size * SL_BUFFER_RATIO) if side == 0 else (ob_top + gap_size * SL_BUFFER_RATIO)
            else:
                continue

            if use_liquidity_tp:
                tp = liquidity_tp(closes, highs, lows, i, side, entry)
                if tp is None:
                    continue
            else:
                tp_dist = abs(entry - sl) * 2.0
                tp = entry + tp_dist if side == 0 else entry - tp_dist

            if side == 0 and (tp <= entry or sl >= entry):
                continue
            if side == 1 and (tp >= entry or sl <= entry):
                continue

            if apply_vetos:
                cand = build_candidate(symbol, side, entry)
                try:
                    v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True
                if not v_ok:
                    continue

            # Simular vela a vela desde i+1 hasta TP/SL o fin de datos.
            close_idx, close_px = None, None
            for j in range(i + 1, min(i + 1 + 300, len(rows))):
                h, l = highs[j], lows[j]
                hit_tp = (h >= tp) if side == 0 else (l <= tp)
                hit_sl = (l <= sl) if side == 0 else (h >= sl)
                if hit_tp and hit_sl:
                    close_idx, close_px = j, sl  # ambiguo en la misma vela -> conservador
                    break
                if hit_tp:
                    close_idx, close_px = j, tp
                    break
                if hit_sl:
                    close_idx, close_px = j, sl
                    break
            if close_idx is None:
                continue  # nunca resolvio (timeout), no se cuenta

            qty = MARGIN / entry
            gross = qty * (close_px - entry) if side == 0 else qty * (entry - close_px)
            fees = (qty * entry + qty * close_px) * FEE
            all_trades.append({
                "symbol": symbol, "pnl": gross - fees, "side": side,
                "open_time": open_times[i], "close_time": open_times[close_idx],
            })
            occupied_until = close_idx

    print(f"  señales de mitigacion de OB encontradas: {n_signals} | pasaron POC: {n_poc_pass if apply_poc_filter else 'n/a'} | trades resueltos: {len(all_trades)}")
    return _apply_capital_sim(all_trades)


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    days = (t1 - t0) / (1000 * 60 * 60 * 24)
    print(f"Universo: {len(basket)} simbolos | {days:.0f} dias reales | Order Block + BOS (LONG+SHORT, ambos lados)")

    trades = backtest_orderblock(conn, basket, apply_vetos=True, use_liquidity_tp=True)
    res = evaluate(trades, days)
    print(f"\n=== Order Block + BOS + TP liquidez real ===")
    print(f"n={res.get('n')} WR={res.get('wr_pct')}% $/mes={res.get('monthly')} "
          f"h1={res.get('pnl_h1')} h2={res.get('pnl_h2')} passes_bar={res.get('passes_bar')} "
          f"stable={res.get('stable_between_halves')}")


if __name__ == "__main__":
    main()

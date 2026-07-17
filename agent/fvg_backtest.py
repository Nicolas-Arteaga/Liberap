"""
Backtest de FVG contra klines históricos cacheados (kline_cache.py), en el
mismo espíritu que backtest_engine.py (MaGeometry) pero para esta estrategia.

python-service/fvg/analyzer.py vive en otro paquete (imports relativos,
depende de shared_kline_cache.py y de FastAPI/pydantic corriendo ahí) — en
vez de arrastrar esa dependencia entera, se REIMPLEMENTA acá la misma regla
exacta (mismas constantes, mismas fórmulas), leída directo de ese archivo:
  - detect_fvgs (gap de 3 velas, detector.py)
  - _entry_status / _is_trend_aligned / _liquidity_target / SL estructural
    (analyzer.py, ver constantes copiadas abajo con su origen)
No se reimplementa la variante IFVG (inversión de gap invalidado) — es un
refinamiento secundario, no el mecanismo principal.

Uso:
    python fvg_backtest.py --symbols BTCUSDT,ETHUSDT --interval 15m
    python fvg_backtest.py --symbols-file symbols_15m.txt --interval 1m --quiet

Limitaciones (además de las ya listadas en backtest_engine.py):
  - No reproduce IFVG ni el ranking completo de top-5 — a cada vela, si hay
    más de una zona accionable simultánea, se toma la de mayor tp_distance_pct
    (mismo criterio que sort_by="range" que usa el agente en vivo).
  - Ventana de escaneo acotada a 200 velas (limit=200, igual que usa
    _scored_zones_for_interval en producción) — no mira gaps más viejos.
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional

from kline_cache import get_cache

# ── Constantes copiadas 1:1 de python-service/fvg/analyzer.py y detector.py ──
MIN_GAP_PCT = 0.0008            # detector.py MIN_GAP_PCT_DEFAULT
ENTRY_APPROACH_PCT = 0.5        # analyzer.py
FRESH_FILL_MAX_PCT = 40.0       # analyzer.py
SL_BUFFER_RATIO = 0.15          # analyzer.py
TP_PROJECTION_RATIO = 2.0       # analyzer.py
RECENT_IMPULSE_LOOKBACK = 40    # analyzer.py
DISPROPORTION_RATIO = 1.5       # analyzer.py
FADING_IMPULSE_TARGET_RATIO = 0.5  # analyzer.py
TP_HAIRCUT_RATIO = 0.9          # analyzer.py
MA_CORRECTION_FAST_SPAN = 25    # analyzer.py
MA_CORRECTION_SLOW_SPAN = 50    # analyzer.py
SCAN_WINDOW = 200               # analyzer.py _scored_zones_for_interval(limit=200)


def _ema_full(closes: list, span: int) -> list:
    """EMA sobre la serie completa, una sola vez (evita recalcular por vela)."""
    alpha = 2.0 / (span + 1)
    out = [closes[0]]
    for c in closes[1:]:
        out.append(alpha * c + (1 - alpha) * out[-1])
    return out


def _detect_open_gaps(highs, lows, closes, lo, hi) -> list:
    """
    Gaps de 3 velas sin rellenar, formados entre [lo, hi] (índices absolutos),
    evaluando el relleno solo con velas <= hi -- nunca futuras. Mismo criterio
    que detect_fvgs() de detector.py.
    """
    zones = []
    for k in range(max(2, lo), hi + 1):
        bullish = lows[k] > highs[k - 2]
        bearish = highs[k] < lows[k - 2]
        if not (bullish or bearish):
            continue
        top, bottom = (lows[k], highs[k - 2]) if bullish else (lows[k - 2], highs[k])
        if top <= bottom:
            continue
        ref = closes[k] or 1.0
        gap_pct = (top - bottom) / ref
        if gap_pct < MIN_GAP_PCT:
            continue

        direction = "bullish" if bullish else "bearish"
        filled = False
        for j in range(k + 1, hi + 1):
            if direction == "bullish" and lows[j] <= bottom:
                filled = True
                break
            if direction == "bearish" and highs[j] >= top:
                filled = True
                break
        if filled:
            continue
        zones.append({"direction": direction, "top": top, "bottom": bottom, "formed_idx": k})
    return zones


def _entry_status(zone, current_price):
    top, bottom = zone["top"], zone["bottom"]
    if bottom <= current_price <= top:
        return "IN_ZONE"
    dist = (current_price - top) if current_price > top else (bottom - current_price)
    dist_pct = abs(dist) / current_price * 100.0 if current_price else 999.0
    return "APPROACHING" if dist_pct <= ENTRY_APPROACH_PCT else "FAR"


def _is_trend_aligned(zone, current_price, ema25_now, ema50_now):
    if ema25_now is None:
        return True
    if zone["direction"] == "bullish":
        return not (current_price < ema25_now and current_price < ema50_now)
    return not (current_price > ema25_now and current_price > ema50_now)


def _liquidity_target(zone, highs, lows, lo, hi, ema25_now, ema50_now):
    """Réplica de _liquidity_target de analyzer.py, ver ese archivo para el razonamiento completo."""
    gap_size = zone["top"] - zone["bottom"]
    window_highs, window_lows = highs[lo:hi + 1], lows[lo:hi + 1]
    recent_highs = window_highs[-RECENT_IMPULSE_LOOKBACK:]
    recent_lows = window_lows[-RECENT_IMPULSE_LOOKBACK:]

    if zone["direction"] == "bullish":
        entry_edge = zone["top"]
        swing_high = max(window_highs)
        local_high = max(recent_highs)
        if swing_high <= entry_edge or local_high <= entry_edge:
            raw_target = entry_edge + gap_size * TP_PROJECTION_RATIO
        else:
            local_reach = local_high - entry_edge
            full_reach = swing_high - entry_edge
            raw_target = (entry_edge + full_reach * FADING_IMPULSE_TARGET_RATIO
                           if full_reach > local_reach * DISPROPORTION_RATIO else swing_high)
        if ema25_now is not None and entry_edge < ema25_now and entry_edge < ema50_now:
            ma_target = min(ema25_now, ema50_now)
            if ma_target < raw_target:
                raw_target = ma_target
        return entry_edge + (raw_target - entry_edge) * TP_HAIRCUT_RATIO
    else:
        entry_edge = zone["bottom"]
        swing_low = min(window_lows)
        local_low = min(recent_lows)
        if swing_low >= entry_edge or local_low >= entry_edge:
            raw_target = entry_edge - gap_size * TP_PROJECTION_RATIO
        else:
            local_reach = entry_edge - local_low
            full_reach = entry_edge - swing_low
            raw_target = (entry_edge - full_reach * FADING_IMPULSE_TARGET_RATIO
                           if full_reach > local_reach * DISPROPORTION_RATIO else swing_low)
        if ema25_now is not None and entry_edge > ema25_now and entry_edge > ema50_now:
            ma_target = max(ema25_now, ema50_now)
            if ma_target > raw_target:
                raw_target = ma_target
        return entry_edge - (entry_edge - raw_target) * TP_HAIRCUT_RATIO


@dataclass
class FvgTrade:
    symbol: str
    side: int
    entry_idx: int
    entry_price: float
    sl_price: float
    tp_price: float
    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None


@dataclass
class FvgResult:
    symbol: str
    trades: list = field(default_factory=list)
    candles_available: int = 0

    def summary(self) -> dict:
        closed = [t for t in self.trades if t.exit_price is not None]
        wins = [t for t in closed if t.pnl_pct and t.pnl_pct > 0]
        losses = [t for t in closed if t.pnl_pct and t.pnl_pct <= 0]
        total_win = sum(t.pnl_pct for t in wins)
        total_loss = abs(sum(t.pnl_pct for t in losses))
        return {
            "symbol": self.symbol,
            "candles_available": self.candles_available,
            "total_trades": len(closed),
            "win_rate_pct": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
            "total_pnl_pct": round(sum(t.pnl_pct for t in closed), 2),
            "profit_factor": (
                round(total_win / total_loss, 2) if total_loss > 0
                else (float("inf") if total_win > 0 else 0.0)
            ),
        }


def run_fvg_backtest(symbol: str, interval: str, klines: Optional[list] = None) -> FvgResult:
    cache = get_cache()
    if klines is None:
        klines = cache.get_klines(symbol, interval, limit=100_000)
    result = FvgResult(symbol=symbol, candles_available=len(klines))
    if len(klines) < MA_CORRECTION_SLOW_SPAN + 10:
        return result

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    n = len(klines)
    ema25_full = _ema_full(closes, MA_CORRECTION_FAST_SPAN)
    ema50_full = _ema_full(closes, MA_CORRECTION_SLOW_SPAN)

    open_trade: Optional[FvgTrade] = None
    i = MA_CORRECTION_SLOW_SPAN
    while i < n:
        if open_trade:
            hi_p, lo_p = highs[i], lows[i]
            if open_trade.side == 0:  # LONG
                if lo_p <= open_trade.sl_price:
                    open_trade.exit_price = open_trade.sl_price
                elif hi_p >= open_trade.tp_price:
                    open_trade.exit_price = open_trade.tp_price
            else:  # SHORT
                if hi_p >= open_trade.sl_price:
                    open_trade.exit_price = open_trade.sl_price
                elif lo_p <= open_trade.tp_price:
                    open_trade.exit_price = open_trade.tp_price

            if open_trade.exit_price is not None:
                if open_trade.side == 0:
                    open_trade.pnl_pct = (open_trade.exit_price - open_trade.entry_price) / open_trade.entry_price * 100.0
                else:
                    open_trade.pnl_pct = (open_trade.entry_price - open_trade.exit_price) / open_trade.entry_price * 100.0
                result.trades.append(open_trade)
                open_trade = None
            i += 1
            continue

        lo_idx = max(0, i - SCAN_WINDOW + 1)
        current_price = closes[i]
        zones = _detect_open_gaps(highs, lows, closes, lo_idx, i)
        best = None
        best_tp_dist = -1.0
        for z in zones:
            status = _entry_status(z, current_price)
            if status not in ("IN_ZONE", "APPROACHING"):
                continue
            if not _is_trend_aligned(z, current_price, ema25_full[i], ema50_full[i]):
                continue
            tp = _liquidity_target(z, highs, lows, lo_idx, i, ema25_full[i], ema50_full[i])
            side = 0 if z["direction"] == "bullish" else 1
            if side == 0 and tp <= current_price:
                continue
            if side == 1 and tp >= current_price:
                continue
            tp_dist_pct = abs(tp - current_price) / current_price * 100.0
            if tp_dist_pct > best_tp_dist:
                best_tp_dist = tp_dist_pct
                gap_size = z["top"] - z["bottom"]
                sl = (z["bottom"] - gap_size * SL_BUFFER_RATIO) if side == 0 else (z["top"] + gap_size * SL_BUFFER_RATIO)
                best = (side, tp, sl)

        if best:
            side, tp, sl = best
            valid = (side == 0 and sl < current_price < tp) or (side == 1 and tp < current_price < sl)
            if valid:
                open_trade = FvgTrade(symbol, side, i, current_price, sl, tp)
        i += 1

    return result


def main():
    parser = argparse.ArgumentParser(description="Backtest de FVG contra klines históricos cacheados.")
    parser.add_argument("--symbols")
    parser.add_argument("--symbols-file")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.symbols_file:
        with open(args.symbols_file, "r", encoding="utf-8") as f:
            symbols = f.read().strip().split(",")
    elif args.symbols:
        symbols = args.symbols.split(",")
    else:
        print("Necesitás --symbols o --symbols-file", file=sys.stderr)
        sys.exit(1)

    print(f"=== FVG Backtest @ {args.interval} ===\n")
    all_trades = []
    symbols_with_trades = 0
    for symbol in symbols:
        symbol = symbol.strip()
        if not symbol:
            continue
        result = run_fvg_backtest(symbol, args.interval)
        s = result.summary()
        if s["total_trades"] > 0:
            symbols_with_trades += 1
            all_trades.extend([t for t in result.trades if t.exit_price is not None])
            if not args.quiet:
                print(
                    f"{symbol:14s} | velas={s['candles_available']:6d} | trades={s['total_trades']:4d} | "
                    f"win_rate={s['win_rate_pct']:6.2f}% | pnl_total={s['total_pnl_pct']:8.2f}% | "
                    f"profit_factor={s['profit_factor']}"
                )

    if all_trades:
        wins = [t for t in all_trades if t.pnl_pct and t.pnl_pct > 0]
        losses = [t for t in all_trades if t.pnl_pct and t.pnl_pct <= 0]
        total_win = sum(t.pnl_pct for t in wins)
        total_loss = abs(sum(t.pnl_pct for t in losses))
        pf = round(total_win / total_loss, 2) if total_loss > 0 else float("inf")
        print(f"\n=== TOTAL FVG @ {args.interval} ===")
        print(f"Símbolos con trades: {symbols_with_trades} | Trades totales: {len(all_trades)}")
        print(f"Win rate: {len(wins) / len(all_trades) * 100:.2f}% ({len(wins)}W / {len(losses)}L)")
        print(f"PnL total (suma simple, sin compounding): {sum(t.pnl_pct for t in all_trades):.2f}%")
        print(f"Profit factor: {pf}")
    else:
        print("\nNingún trade generado en el rango probado.")


if __name__ == "__main__":
    main()

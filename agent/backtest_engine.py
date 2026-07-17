"""
Backtest Engine — replay de estrategias MaGeometry contra velas históricas
ya cacheadas en kline_cache.py (SQLite), en vez de contra precio en vivo.

Reusa la lógica REAL de detección (VergeAgent._evaluate_ma_geometry_profile,
_sma_series, _normalized_slope_angle) importándola de verge_agent.py — no la
reimplementa, para que el resultado sea fiel a lo que el agente haría en
producción con ese mismo PatternParamsJson.

Uso:
    python backtest_engine.py --profile-id <uuid> --symbols BTCUSDT,ETHUSDT --interval 15m
    python backtest_engine.py --profile-json perfil.json --symbols BTCUSDT --interval 1h

Limitaciones conocidas (leer antes de confiar ciegamente en los números):
  - Solo cubre perfiles StrategyType=MaGeometry por ahora (FVG/ADN quedan
    para una segunda vuelta si esto sirve).
  - TP simplificado: RR×SL con piso min_tp_pct, SIN el recorte estructural
    que sí aplica risk_manager.py en vivo (_apply_structural_tp_cap). Un TP
    más lejano es más difícil de alcanzar que uno recortado, así que el
    win rate acá tiende a ser IGUAL o MÁS CONSERVADOR que en producción,
    nunca más optimista por este motivo — pero no es un clon 1:1.
  - No modela slippage ni comisiones — el profit factor real en vivo será
    algo peor que el que muestra este número.
  - Una posición abierta por símbolo a la vez (no simula overlap de
    MaxOpenPositions=N del perfil).
  - La cobertura histórica depende de lo que el agente haya acumulado en
    kline_cache.py corriendo en vivo — no es un dataset bajado a propósito.
"""
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

from kline_cache import get_cache

MIN_CANDLES_FOR_MA99 = 110  # MA99 necesita 99 velas + margen para medir pendiente


def _make_geo_reader():
    """
    Instancia VergeAgent SIN correr __init__ (evita conectar a DB/backend/auth
    — todo eso es innecesario acá). Los métodos que reusamos
    (_evaluate_ma_geometry_profile, _sma_series, _normalized_slope_angle,
    _calculate_ma99_slope_angle, _pct_distance) no dependen de ningún estado
    seteado en __init__, solo de los dicts de clase _MA_SERIES_KEYS/_MA_NOW_KEYS
    y de sus propios argumentos.
    """
    from verge_agent import VergeAgent
    return object.__new__(VergeAgent)


@dataclass
class BacktestTrade:
    symbol: str
    side: int  # 0=LONG, 1=SHORT
    entry_idx: int
    entry_price: float
    sl_price: float
    tp_price: float
    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None


@dataclass
class BacktestResult:
    profile_name: str
    symbol: str
    trades: list = field(default_factory=list)
    candles_available: int = 0

    @property
    def closed(self):
        return [t for t in self.trades if t.exit_price is not None]

    def summary(self) -> dict:
        closed = self.closed
        wins = [t for t in closed if t.pnl_pct and t.pnl_pct > 0]
        losses = [t for t in closed if t.pnl_pct and t.pnl_pct <= 0]
        total_win_pct = sum(t.pnl_pct for t in wins)
        total_loss_pct = abs(sum(t.pnl_pct for t in losses))
        return {
            "profile": self.profile_name,
            "symbol": self.symbol,
            "candles_available": self.candles_available,
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
            "avg_win_pct": round(total_win_pct / len(wins), 3) if wins else 0.0,
            "avg_loss_pct": round(-total_loss_pct / len(losses), 3) if losses else 0.0,
            "total_pnl_pct": round(sum(t.pnl_pct for t in closed), 2),
            "profit_factor": (
                round(total_win_pct / total_loss_pct, 2) if total_loss_pct > 0
                else (float("inf") if total_win_pct > 0 else 0.0)
            ),
        }


# Ventana de "cola" que se le pasa a _evaluate_ma_geometry_profile para
# calcular pendientes/lookbacks (slope windowCandles, peakProximity
# lookbackCandles, exit slLookbackCandles, contextSlope windowCandles —
# todos <=12 en los perfiles reales). Generoso a propósito.
_SUFFIX_LEN = 50


def _precompute_ma_series(agent, closes: list) -> dict:
    """
    Calcula cada SMA UNA sola vez sobre la serie completa (ya es O(n) gracias
    al truco de suma acumulada en _sma_series) en vez de recortar y volver a
    calcular en cada vela — eso era O(n²) y no escalaba a 400 símbolos.
    full[period][j] = SMA que termina en el índice de vela (j + period - 1).
    """
    return {
        7:  agent._sma_series(closes, 7),
        25: agent._sma_series(closes, 25),
        50: agent._sma_series(closes, 50),
        99: agent._sma_series(closes, 99),
    }


def _build_geo_at(ma_full, highs, lows, closes, symbol, i):
    """
    Arma el mismo dict 'geo' que _read_ma_geometry produce en vivo, usando
    SOLO datos hasta el índice i inclusive (nunca futuros — sin lookahead),
    indexando en las series ya precalculadas en vez de recortar+recalcular.
    """
    j99 = i - 98
    if j99 < 0:
        return None
    j7, j25, j50 = i - 6, i - 24, i - 49

    def tail(series, j):
        return series[max(0, j - _SUFFIX_LEN): j + 1]

    s7, s25, s50, s99 = tail(ma_full[7], j7), tail(ma_full[25], j25), tail(ma_full[50], j50), tail(ma_full[99], j99)
    if not (s7 and s25 and s50 and s99):
        return None

    lo = max(0, i - _SUFFIX_LEN)
    return {
        "symbol": symbol,
        "current_price": closes[i],
        "current_high": highs[i],
        "current_low": lows[i],
        "highs": highs[lo: i + 1],
        "lows": lows[lo: i + 1],
        "ma7_now": s7[-1], "ma25_now": s25[-1], "ma50_now": s50[-1], "ma99_now": s99[-1],
        "ma7_series": s7, "ma25_series": s25, "ma50_series": s50, "ma99_series": s99,
    }


def run_backtest(
    profile: dict, symbol: str, interval: str, klines: Optional[list] = None,
    breakeven_sl: bool = False, fee_pct: float = 0.0,
) -> BacktestResult:
    """
    profile: dict con al menos name/patternParamsJson/minConfluenceScore/
             allowLong/allowShort (mismas claves camelCase que ya usa
             _evaluate_ma_geometry_profile en vivo).
    klines: opcional, para tests; si no se pasa, se lee de kline_cache.py.
    """
    agent = _make_geo_reader()
    result = BacktestResult(profile_name=profile.get("name", "?"), symbol=symbol)

    if klines is None:
        cache = get_cache()
        klines = cache.get_klines(symbol, interval, limit=100_000)

    result.candles_available = len(klines)
    if len(klines) < MIN_CANDLES_FOR_MA99 + 5:
        return result

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    ma_full = _precompute_ma_series(agent, closes)

    open_trade: Optional[BacktestTrade] = None
    i = MIN_CANDLES_FOR_MA99
    n = len(klines)
    while i < n:
        if open_trade:
            hi, lo = highs[i], lows[i]
            if open_trade.side == 0:  # LONG
                if lo <= open_trade.sl_price:
                    open_trade.exit_idx, open_trade.exit_price, open_trade.exit_reason = i, open_trade.sl_price, "SL"
                elif hi >= open_trade.tp_price:
                    open_trade.exit_idx, open_trade.exit_price, open_trade.exit_reason = i, open_trade.tp_price, "TP"
            else:  # SHORT
                if hi >= open_trade.sl_price:
                    open_trade.exit_idx, open_trade.exit_price, open_trade.exit_reason = i, open_trade.sl_price, "SL"
                elif lo <= open_trade.tp_price:
                    open_trade.exit_idx, open_trade.exit_price, open_trade.exit_reason = i, open_trade.tp_price, "TP"

            if open_trade.exit_price is not None:
                if open_trade.side == 0:
                    open_trade.pnl_pct = (open_trade.exit_price - open_trade.entry_price) / open_trade.entry_price * 100.0
                else:
                    open_trade.pnl_pct = (open_trade.entry_price - open_trade.exit_price) / open_trade.entry_price * 100.0
                result.trades.append(open_trade)
                open_trade = None
            i += 1
            continue

        geo = _build_geo_at(ma_full, highs, lows, closes, symbol, i)
        if geo:
            candidate = agent._evaluate_ma_geometry_profile(profile, geo)
            if candidate:
                side = candidate["side"]
                entry_price = geo["current_price"]
                sl_price = candidate["custom_sl_price"]
                min_tp_pct = float(candidate.get("min_tp_pct", 10.0)) / 100.0
                sl_dist = abs(entry_price - sl_price)
                # Simplificado: RR 3x sobre el SL o el piso min_tp_pct, lo que
                # sea mayor -- ver limitación documentada arriba (no reproduce
                # _apply_structural_tp_cap de risk_manager.py).
                tp_dist = max(sl_dist * 3.0, entry_price * min_tp_pct)
                tp_price = entry_price + tp_dist if side == 0 else entry_price - tp_dist
                open_trade = BacktestTrade(symbol, side, i, entry_price, sl_price, tp_price)
        i += 1

    return result


def load_profile_from_db(profile_id: str) -> dict:
    """
    Trae un StrategyProfile de Postgres (vía docker exec + psql, sin
    necesitar un driver de DB instalado) ya en las claves camelCase que
    espera _evaluate_ma_geometry_profile.
    """
    query = (
        "SELECT row_to_json(t) FROM (SELECT "
        '"Name" AS name, "PatternParamsJson" AS "patternParamsJson", '
        '"MinConfluenceScore" AS "minConfluenceScore", '
        '"AllowLong" AS "allowLong", "AllowShort" AS "allowShort" '
        'FROM "StrategyProfiles" WHERE "Id" = \'' + profile_id + "') t;"
    )
    out = subprocess.run(
        ["docker", "exec", "verge-db", "psql", "-U", "postgres", "-d", "Verge", "-t", "-A", "-c", query],
        capture_output=True, text=True, check=True,
    )
    line = out.stdout.strip()
    if not line:
        raise ValueError(f"Profile {profile_id} not found")
    return json.loads(line)


def main():
    parser = argparse.ArgumentParser(description="Backtest de perfiles MaGeometry contra klines históricos cacheados.")
    parser.add_argument("--profile-id", help="GUID del StrategyProfile en Postgres")
    parser.add_argument("--profile-json", help="Path a un JSON con el perfil (alternativa a --profile-id)")
    parser.add_argument("--symbols", help="Lista separada por comas, ej. BTCUSDT,ETHUSDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--quiet", action="store_true", help="Solo imprime el TOTAL agregado, no línea por símbolo")
    parser.add_argument("--symbols-file", help="Path a un .txt con símbolos separados por coma (para listas largas)")
    args = parser.parse_args()

    if args.symbols_file:
        with open(args.symbols_file, "r", encoding="utf-8") as f:
            args.symbols = f.read().strip()
    elif not args.symbols:
        print("Necesitás --symbols o --symbols-file", file=sys.stderr)
        sys.exit(1)

    if args.profile_id:
        profile = load_profile_from_db(args.profile_id)
    elif args.profile_json:
        with open(args.profile_json, "r", encoding="utf-8") as f:
            profile = json.load(f)
    else:
        print("Necesitás --profile-id o --profile-json", file=sys.stderr)
        sys.exit(1)

    print(f"=== Backtest: {profile.get('name')} @ {args.interval} ===\n")
    all_trades = []
    symbols_with_trades = 0
    for symbol in args.symbols.split(","):
        symbol = symbol.strip()
        if not symbol:
            continue
        result = run_backtest(profile, symbol, args.interval)
        s = result.summary()
        if s["total_trades"] > 0:
            symbols_with_trades += 1
            all_trades.extend(result.closed)
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
        print(f"\n=== TOTAL: {profile.get('name')} @ {args.interval} ===")
        print(f"Símbolos con trades: {symbols_with_trades} | Trades totales: {len(all_trades)}")
        print(f"Win rate: {len(wins) / len(all_trades) * 100:.2f}% ({len(wins)}W / {len(losses)}L)")
        print(f"PnL total (suma simple, sin compounding): {sum(t.pnl_pct for t in all_trades):.2f}%")
        print(f"Profit factor: {pf}")
    else:
        print("\nNingún trade generado en el rango probado.")


if __name__ == "__main__":
    main()

"""
Motor de backtest GENERICO — reusa el codigo REAL de produccion
(agent/verge_agent.py para evaluar candidatos, agent/risk_manager.py para
SL/TP/qty) contra klines historicos de agent/data/binance_vision_clean.db.

Por que existe esto: los backtests de hoy (ma_slope_backtest.py,
fvg_short_backtest.py) reimplementaban la logica a mano, y eso ya causo un
bug real (Caso 3: el backtest a mano se salteo el tope estructural de TP de
risk_manager.py, que SI aplica a ma_slope_mode). Este motor NO reimplementa
nada: instancia las clases reales (VergeAgent, RiskManager) y les inyecta un
"fetcher" que sirve datos historicos en vez de pegarle a Binance en vivo.

Resolucion base 2026-07-26: el agente real re-evalua cada 5 min
(LOOP_INTERVAL_SECONDS=300) -- con paso de 15m el motor generaba ~1.7
señales/dia en TODO el universo vs ~3.6 trades/dia aceptados reales en MA
Slope Caso 3 (auditado 11-25/7, 51 trades). El "ojo" (deteccion de patron)
ahora camina sobre klines_5m; klines_clean (15m) se mantiene SOLO para lo
que produccion pide explicitamente en 15m (precio actual, tope estructural
de TP via get_klines_for_nexus).

Primer alcance: StrategyType=MaGeometry (ver PROGRESS_LOG / plan de sesion).
Los demas tipos (FVG, AdnCompression, ArrowPeak, GoldenUTurn, TotalSweep) se
agregan despues con el mismo patron.
"""
import os
import sys
import sqlite3
import math
import bisect
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python-service"))

from verge_agent import VergeAgent  # noqa: E402
from risk_manager import RiskManager  # noqa: E402
import config as agent_config  # noqa: E402
from fvg.analyzer import FvgAnalyzer  # noqa: E402
from adn_compression.analyzer import AdnCompressionAnalyzer  # noqa: E402

# verge_agent.py configura logging a archivo con rotacion al importarse (para
# el agente EN VIVO) -- en un backtest eso genera miles de writes a disco y
# frena todo (confirmado: 2+ min para 10 candidatos en un solo simbolo). No
# se toca verge_agent.py (es el agente real); se apaga el ruido solo aca.
logging.getLogger().setLevel(logging.ERROR)
for _name in ("VergeAgent", "RiskManager"):
    logging.getLogger(_name).setLevel(logging.ERROR)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")

# Base de caminata (deteccion de señal) -- 5m, igual que el loop real.
BASE_INTERVAL = "5m"
BASE_MS = 5 * 60 * 1000
BASE_TABLE = "klines_5m"

# 15m sigue existiendo para lo que produccion pide EXPLICITAMENTE en 15m
# (precio actual, tope estructural de TP) independientemente de que tan
# seguido se re-evalue el patron.
CAP_INTERVAL = "15m"
CAP_MS = 15 * 60 * 1000
CAP_TABLE = "klines_clean"

FEE_PER_SIDE = 0.0004  # 0.04%, mismo supuesto usado en todos los capital-sims de hoy

# Top 40 por capitalizacion/liquidez real (mismo criterio ya usado para el
# backtest de FVG large-cap de hoy, agent/download_binance_vision.py) --
# pedido del usuario: poder testear solo estos en vez de los 400+ del
# watchlist completo (mucho menos ruido de pares chicos/ilíquidos).
TOP_40_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "SUIUSDT", "INJUSDT", "TIAUSDT", "SEIUSDT", "FILUSDT",
    "ETCUSDT", "TRXUSDT", "BCHUSDT", "UNIUSDT", "AAVEUSDT", "MKRUSDT", "RUNEUSDT",
    "FTMUSDT", "GALAUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT", "CHZUSDT", "ENJUSDT",
    "XLMUSDT", "ALGOUSDT", "VETUSDT", "EOSUSDT", "WLDUSDT",
]

_INTERVAL_MS = {"5m": BASE_MS, "15m": CAP_MS, "1h": 3600_000, "4h": 14400_000, "1d": 86400_000}


class HistoricalFetcher:
    """
    Reemplaza al fetcher en vivo (multi_source_fetcher) que usan VergeAgent y
    RiskManager. Sirve SIEMPRE datos hasta `now_ms` (nunca futuro).
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.now_ms = 0
        self._cache_base: dict[str, list] = {}   # symbol -> filas 5m
        self._cache_cap: dict[str, list] = {}     # symbol -> filas 15m (klines_clean)
        self._cache_resampled: dict[tuple, list] = {}
        self._cache_multi: dict[tuple, list] = {}
        # simbolo actual "activo" durante el walk -- permite busqueda binaria
        # en vez de reescanear toda la serie en cada llamada (bug real
        # 2026-07-26: O(n) por llamada x O(n) llamadas = O(n^2)).
        self._active_symbol = None
        self._active_by_interval: dict[str, tuple] = {}  # interval -> (rows, times), resampleado desde BASE (5m)

    def set_now(self, now_ms: int):
        self.now_ms = now_ms

    def set_active_symbol(self, symbol: str, intervals: tuple = ()):
        """Fija el simbolo activo durante el walk -- precalcula rows+open_times
        (resampleadas desde la base de 5m) UNA vez por intervalo relevante."""
        if self._active_symbol == symbol and all(iv in self._active_by_interval for iv in intervals):
            return
        if self._active_symbol != symbol:
            self._active_by_interval = {}
            self._active_symbol = symbol
        base_rows = self._load_base(symbol)
        for iv in intervals:
            if iv in self._active_by_interval:
                continue
            rows = base_rows if iv == BASE_INTERVAL else self._resample(base_rows, iv)
            self._active_by_interval[iv] = (rows, [r[0] for r in rows])

    def _load_base(self, symbol: str) -> list:
        if symbol not in self._cache_base:
            cur = self.conn.cursor()
            cur.execute(
                f"SELECT open_time, open, high, low, close, volume FROM {BASE_TABLE} "
                "WHERE symbol=? AND interval=? ORDER BY open_time ASC",
                (symbol, BASE_INTERVAL),
            )
            self._cache_base[symbol] = cur.fetchall()
        return self._cache_base[symbol]

    def _load_cap15m(self, symbol: str) -> list:
        if symbol not in self._cache_cap:
            cur = self.conn.cursor()
            cur.execute(
                f"SELECT open_time, open, high, low, close, volume FROM {CAP_TABLE} "
                "WHERE symbol=? AND interval=? ORDER BY open_time ASC",
                (symbol, CAP_INTERVAL),
            )
            self._cache_cap[symbol] = cur.fetchall()
        return self._cache_cap[symbol]

    def _resample(self, base_rows: list, interval: str) -> list:
        """Agrega velas base (5m) a `interval`, alineado a calendario."""
        if interval == BASE_INTERVAL:
            return base_rows
        mult = _INTERVAL_MS[interval] // BASE_MS
        cache_key = (id(base_rows), interval)
        if cache_key in self._cache_resampled:
            return self._cache_resampled[cache_key]
        bucket_ms = BASE_MS * mult
        buckets: dict[int, list] = {}
        for r in base_rows:
            b = r[0] - (r[0] % bucket_ms)
            buckets.setdefault(b, []).append(r)
        out = []
        for b in sorted(buckets.keys()):
            g = sorted(buckets[b], key=lambda r: r[0])
            if len(g) != mult:
                continue
            ok = all(g[i + 1][0] - g[i][0] == BASE_MS for i in range(len(g) - 1))
            if not ok:
                continue
            out.append((b, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)))
        self._cache_resampled[cache_key] = out
        return out

    def get_klines_with_partial(self, symbol: str, interval: str, limit: int) -> list:
        """
        IGUAL que produccion: Binance devuelve la vela EN FORMACION como el
        ultimo elemento (open=apertura real, high/low/close = lo que lleva
        acumulado hasta el instante de la consulta). Construye la vela
        parcial de `interval` a partir de las sub-velas de 5m ya cerradas
        dentro del bucket actual (sin look-ahead).
        """
        if interval == BASE_INTERVAL:
            rows, cutoff_idx = self._closed_upto_base(symbol)
            start = max(0, cutoff_idx - limit)
            return rows[start:cutoff_idx]

        mult = _INTERVAL_MS[interval] // BASE_MS
        bucket_ms = BASE_MS * mult

        rows_base, times_base = self._active_by_interval[BASE_INTERVAL]
        full_rows, full_times = self._active_by_interval[interval]

        cutoff_base = bisect.bisect_right(times_base, self.now_ms - BASE_MS)
        cutoff_full = bisect.bisect_right(full_times, self.now_ms - bucket_ms)
        full = full_rows[:cutoff_full]

        last_full_end = full[-1][0] + bucket_ms if full else None
        start_idx_base = 0 if last_full_end is None else bisect.bisect_left(times_base, last_full_end)
        partial_bucket = rows_base[start_idx_base:cutoff_base]

        result = full
        if partial_bucket:
            g = partial_bucket
            result = full + [(g[0][0], g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g))]
        return result[-limit:]

    def _closed_upto_base(self, symbol: str):
        if self._active_symbol == symbol and BASE_INTERVAL in self._active_by_interval:
            rows, times = self._active_by_interval[BASE_INTERVAL]
        else:
            rows = self._load_base(symbol)
            times = [r[0] for r in rows]
        cutoff_idx = bisect.bisect_right(times, self.now_ms - BASE_MS)
        return rows, cutoff_idx

    def _closed_upto_cap15m(self, symbol: str):
        rows = self._load_cap15m(symbol)
        times = [r[0] for r in rows]
        cutoff_idx = bisect.bisect_right(times, self.now_ms - CAP_MS)
        return rows, cutoff_idx

    # ── Interfaz que espera verge_agent.py / risk_manager.py ──
    def get_current_price(self, symbol: str) -> float:
        rows, cutoff_idx = self._closed_upto_base(symbol)
        return float(rows[cutoff_idx - 1][4]) if cutoff_idx > 0 else 0.0

    def _load_multi(self, symbol: str, exchange: str) -> list:
        key = (exchange, symbol)
        if key not in self._cache_multi:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT open_time, open, high, low, close, volume FROM klines_multi_exchange "
                "WHERE exchange=? AND symbol=? AND interval=? ORDER BY open_time ASC",
                (exchange, symbol, CAP_INTERVAL),
            )
            self._cache_multi[key] = cur.fetchall()
        return self._cache_multi[key]

    def get_klines_for_nexus(self, symbol: str, interval: str = "15m", limit: int = 400) -> list:
        """
        En produccion esto SIEMPRE devuelve [] (fail-open) para el proposito
        de _apply_structural_tp_cap en ma_slope_mode -- root cause real
        2026-07-26, verificado 1:1 contra 2 trades reales (NVDAUSDT, TRXUSDT):
        con el historial completo (400 velas de 15m, lo que SI tengo yo
        archivado) el tope se activaba y rechazaba via MIN-RR-VETO un trade
        que en la realidad SI abrio con TP=189.072 (yo calculaba 189.0 exacto
        una vez desactivado el tope). La cache en vivo de produccion
        (kline_cache.py) rara vez llega a tener esas 400 velas (~4 dias)
        listas en el momento exacto de la consulta -- el propio codigo real
        (risk_manager.py: "if not klines or len(klines) < 60: return
        tp_price") ya contempla ese fail-open, simplemente no lo estaba
        disparando porque mi archivo historico SIEMPRE tiene datos completos.
        Devolver [] aca fuerza el mismo camino que toma produccion en la
        practica para esta estrategia.
        """
        return []


def make_ma_geometry_agent(fetcher: HistoricalFetcher) -> VergeAgent:
    """
    Instancia VergeAgent SIN correr su __init__ (evita conexiones HTTP/DB en
    vivo) y le pega el fetcher historico donde su codigo real espera pegarle
    a Binance. Reusa _read_ma_geometry / _evaluate_ma_geometry_profile /
    _normalized_slope_angle / _calculate_ma99_slope_angle / _sma_series tal
    cual estan en produccion — ni una linea reimplementada.
    """
    agent = VergeAgent.__new__(VergeAgent)
    agent._fetch_binance_futures_klines_direct = lambda symbol, interval, limit: [
        {"open": k[1], "high": k[2], "low": k[3], "close": k[4], "open_time": k[0]}
        for k in fetcher.get_klines_with_partial(symbol, interval, limit)
    ]
    return agent


def make_fvg_agent(fetcher: HistoricalFetcher) -> VergeAgent:
    """
    Idem make_ma_geometry_agent, pero para StrategyType=FVG. `_build_fvg_candidate`
    usa self.fetcher.get_current_price / get_klines_for_nexus (via
    _compute_compression_snapshot) -- ambos ya sabe servirlos HistoricalFetcher.
    """
    agent = VergeAgent.__new__(VergeAgent)
    agent.fetcher = fetcher
    return agent


def make_fvg_analyzer(fetcher: HistoricalFetcher) -> FvgAnalyzer:
    """FvgAnalyzer real (python-service/fvg/analyzer.py) con _fetch_klines
    monkeypatcheado a datos historicos -- mismo patron que
    agent/fvg_short_backtest.py de hoy, generalizado."""
    analyzer = FvgAnalyzer()
    analyzer._fetch_klines = lambda symbol, interval, limit: [
        [r[0], r[1], r[2], r[3], r[4], r[5]] for r in fetcher.get_klines_with_partial(symbol, interval, limit)
    ]
    return analyzer


def make_adn_agent(fetcher: HistoricalFetcher) -> VergeAgent:
    """Idem make_fvg_agent, para StrategyType=AdnCompression.
    `_build_adn_compression_candidate` no usa self.fetcher directamente
    (solo recibe el item ya armado), pero se mantiene el patron por si
    alguna variante futura lo necesita."""
    agent = VergeAgent.__new__(VergeAgent)
    agent.fetcher = fetcher
    return agent


def make_adn_analyzer(fetcher: HistoricalFetcher) -> AdnCompressionAnalyzer:
    """AdnCompressionAnalyzer real (python-service/adn_compression/analyzer.py)
    con _fetch_klines monkeypatcheado a datos historicos -- mismo patron que
    make_fvg_analyzer."""
    analyzer = AdnCompressionAnalyzer()
    analyzer._fetch_klines = lambda symbol, interval, limit: [
        [r[0], r[1], r[2], r[3], r[4], r[5]] for r in fetcher.get_klines_with_partial(symbol, interval, limit)
    ]
    return analyzer


class BacktestEngine:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.fetcher = HistoricalFetcher(self.conn)
        self.ma_agent = make_ma_geometry_agent(self.fetcher)
        self.fvg_agent = make_fvg_agent(self.fetcher)
        self.fvg_analyzer = make_fvg_analyzer(self.fetcher)
        self.adn_agent = make_adn_agent(self.fetcher)
        self.adn_analyzer = make_adn_analyzer(self.fetcher)
        self.risk_manager = RiskManager(fetcher=self.fetcher)

    def available_symbols(self) -> list:
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval=?", (CAP_INTERVAL,))
        binance_syms = set(r[0] for r in cur.fetchall())
        cur.execute("SELECT DISTINCT symbol FROM klines_5m WHERE interval=?", (BASE_INTERVAL,))
        base_syms = set(r[0] for r in cur.fetchall())
        return sorted(binance_syms & base_syms)

    def top40_symbols(self) -> list:
        """Interseccion de TOP_40_SYMBOLS con lo que realmente tenemos
        cacheado -- preserva el orden de TOP_40_SYMBOLS (por capitalizacion),
        no alfabetico."""
        available = set(self.available_symbols())
        return [s for s in TOP_40_SYMBOLS if s in available]

    def run_ma_geometry(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        shadow_mode: bool = False,
    ) -> dict:
        """StrategyType=MaGeometry. profile: dict con las keys reales de
        StrategyProfile (patternParamsJson, allowLong, allowShort,
        tpMultiplier, slMultiplier, minRR, marginPerTrade, maxOpenPositions,
        name, id)."""
        import json
        params = json.loads(profile.get("patternParamsJson") or "{}")
        interval = params.get("timeframe") or "1h"

        def candidate_fn(symbol):
            geo = self.ma_agent._read_ma_geometry(symbol, interval=interval)
            if not geo:
                return None
            return self.ma_agent._evaluate_ma_geometry_profile(profile, geo)

        return self._run_generic(profile, symbols, start_ms, end_ms, interval,
                                  candidate_fn, balance, progress_cb, shadow_mode)

    def run_fvg(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        shadow_mode: bool = False,
    ) -> dict:
        """
        StrategyType=FVG. Reusa FvgAnalyzer real (python-service/fvg/analyzer.py,
        via make_fvg_analyzer) para detectar la zona + verge_agent.py::
        _build_fvg_candidate para armar el candidato (SL/TP estructural del
        gap) -- mismo patron que agent/fvg_short_backtest.py de hoy,
        integrado al motor generico en vez de un script aparte.
        """
        import json
        params = json.loads(profile.get("patternParamsJson") or "{}")
        interval = params.get("timeframe") or "15m"
        allow_long = profile.get("allowLong", True)
        allow_short = profile.get("allowShort", True)

        def candidate_fn(symbol):
            try:
                item, _reason = self.fvg_analyzer._scan_symbol(symbol, interval, sort_by="range")
            except Exception:
                return None
            if not item:
                return None
            if item.direction == "bullish" and not allow_long:
                return None
            if item.direction == "bearish" and not allow_short:
                return None
            item_dict = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            return self.fvg_agent._build_fvg_candidate(item_dict, profile)

        return self._run_generic(profile, symbols, start_ms, end_ms, interval,
                                  candidate_fn, balance, progress_cb, shadow_mode)

    def run_adn_compression(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        shadow_mode: bool = False,
    ) -> dict:
        """
        StrategyType=AdnCompression. Reusa AdnCompressionAnalyzer real
        (python-service/adn_compression/analyzer.py) + verge_agent.py::
        _build_adn_compression_candidate. Igual que produccion
        (_run_adn_compression_scan): solo genera candidato en fase
        PULLBACK_TO_MA7 y direccion LONG (short queda para mas adelante,
        nunca implementado en produccion tampoco).
        """
        import json
        params = json.loads(profile.get("patternParamsJson") or "{}")
        interval = params.get("timeframe") or "5m"

        def candidate_fn(symbol):
            try:
                item = self.adn_analyzer._analyze_symbol(symbol, interval)
            except Exception:
                return None
            if not item or item.phase != "PULLBACK_TO_MA7" or item.direction != "LONG":
                return None
            item_dict = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            return self.adn_agent._build_adn_compression_candidate(item_dict, profile)

        return self._run_generic(profile, symbols, start_ms, end_ms, interval,
                                  candidate_fn, balance, progress_cb, shadow_mode)

    def _run_generic(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        interval: str,
        candidate_fn: Callable[[str], Optional[dict]],
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        shadow_mode: bool = False,
    ) -> dict:
        """
        Motor de caminata GENERICO -- cualquier StrategyType lo puede usar
        con solo pasarle su propio `candidate_fn(symbol) -> candidato|None`
        (la deteccion de patron especifica de esa estrategia). El resto
        (avance cada 5 min, TP/SL, zombie_timeout, capital limitado,
        shadow_mode) es igual para todas -- ya validado 1:1 contra trades
        reales con MaGeometry (ver PROGRESS_LOG 2026-07-26).
        """
        interval_ms = _INTERVAL_MS[interval]
        min_candles = 150
        min_base_needed = min_candles * (interval_ms // BASE_MS)

        all_trades = []
        shadow_signals = []
        total = len(symbols)
        for idx, symbol in enumerate(symbols):
            self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, interval))
            rows_base, _times_base = self.fetcher._active_by_interval[BASE_INTERVAL]
            n = len(rows_base)
            if n < min_base_needed + 20:
                if progress_cb:
                    progress_cb(idx + 1, total)
                continue

            open_trade = None
            last_trade_day = None
            # avanza cada 5 min -- igual que el loop real (LOOP_INTERVAL_SECONDS=300).
            j = min_base_needed
            while j < n:
                now_ms = rows_base[j][0] + BASE_MS  # cierre de esta sub-vela de 5m
                if now_ms < start_ms:
                    j += 1
                    continue
                if now_ms > end_ms:
                    break

                self.fetcher.set_now(now_ms)

                if open_trade:
                    h, l, c = rows_base[j][2], rows_base[j][3], rows_base[j][4]
                    side = open_trade["side"]
                    hit_tp = (l <= open_trade["tp"]) if side == 1 else (h >= open_trade["tp"])
                    hit_sl = (h >= open_trade["sl"]) if side == 1 else (l <= open_trade["sl"])
                    if hit_tp:
                        all_trades.append({**open_trade, "close_reason": "TP", "close_time": now_ms})
                        open_trade = None
                    elif hit_sl:
                        all_trades.append({**open_trade, "close_reason": "SL", "close_time": now_ms})
                        open_trade = None
                    else:
                        # zombie_timeout -- igual que verge_agent.py:4865-4894:
                        # mas de maxTradeDurationCandles velas de 15m (SIEMPRE
                        # 15m, independiente del timeframe de la estrategia) Y
                        # en perdida -> cierre forzado a mercado. Bug real
                        # 2026-07-26: nunca lo porte al backtest -> trades
                        # colgados hasta 24 dias tapando los 3 slots de
                        # capital, rechazando señales reales que si hubieran
                        # entrado en produccion.
                        max_candles = int(profile.get("maxTradeDurationCandles", 16))
                        candles_open = (now_ms - open_trade["open_time"]) / (15 * 60 * 1000)
                        if candles_open >= max_candles:
                            entry = open_trade["entry"]
                            pnl_pct = (c - entry) / entry if side == 0 else (entry - c) / entry
                            if pnl_pct < 0:
                                all_trades.append({**open_trade, "close_reason": "zombie_timeout",
                                                    "close_time": now_ms, "_zombie_close_price": c})
                                open_trade = None
                                j += 1
                                continue
                        # shadow_mode: diagnostico -- registra si HUBIERA
                        # entrado un candidato valido aca, aunque el simbolo
                        # ya tenga una posicion "abierta" en esta simulacion
                        # (bug real 2026-07-26: una entrada temprana --
                        # a veces un falso positivo propio, ver caso BTCUSDT
                        # 11/7 -- puede tapar en el backtest una señal real
                        # posterior, porque el motor no permite 2 posiciones
                        # simultaneas por simbolo, igual que produccion, pero
                        # sin la falsa entrada esa señal si hubiera contado).
                        if shadow_mode:
                            cand_shadow = candidate_fn(symbol)
                            if cand_shadow:
                                shadow_signals.append({"symbol": symbol, "open_time": now_ms,
                                                        "blocked_by": "open_trade"})
                        j += 1
                        continue

                day_key = datetime.utcfromtimestamp(now_ms / 1000).date()
                if last_trade_day == day_key:
                    j += 1
                    continue

                candidate = candidate_fn(symbol)
                if not candidate:
                    j += 1
                    continue

                risk = self.risk_manager._calculate_position_nexus_style(
                    symbol, candidate, balance, profile
                )
                if not risk:
                    j += 1
                    continue

                open_trade = {
                    "symbol": symbol,
                    "side": risk["side"],
                    "open_time": now_ms,
                    "entry": risk["entry_price"],
                    "sl": risk["sl_price"],
                    "tp": risk["tp_price"],
                    "margin": risk["margin"],
                }
                last_trade_day = day_key
                j += 1

            if progress_cb:
                progress_cb(idx + 1, total)

        result = self._capital_sim(all_trades, profile)
        result["all_signals_raw"] = all_trades
        result["shadow_signals"] = shadow_signals
        return result

    def _capital_sim(self, trades: list, profile: dict) -> dict:
        margin = float(profile.get("marginPerTrade", 150))
        slots = int(profile.get("maxOpenPositions", 3))

        for t in trades:
            qty = margin / t["entry"]
            if t["close_reason"] == "TP":
                close_px = t["tp"]
            elif t["close_reason"] == "zombie_timeout":
                close_px = t["_zombie_close_price"]
            else:
                close_px = t["sl"]
            gross = qty * (close_px - t["entry"]) if t["side"] == 0 else qty * (t["entry"] - close_px)
            fees = (qty * t["entry"] + qty * close_px) * FEE_PER_SIDE
            t["pnl"] = gross - fees

        # Desempate por simbolo (alfabetico) cuando dos señales comparten el
        # mismo open_time -- necesario para que run_parallel de un resultado
        # IDENTICO al secuencial: en paralelo, las señales se combinan en el
        # orden en que cada proceso termina (no determinista), asi que sin
        # este segundo criterio el ganador de un cupo de capital empatado
        # podia variar entre corridas (bug real 2026-07-26: 6790 señales
        # identicas en ambas corridas, pero 466 vs 460 aceptadas y PnL de
        # signo distinto solo por el orden de desempate). available_symbols()
        # ya devuelve la lista ordenada alfabeticamente, que es como el motor
        # secuencial itera -- este sort reproduce ese mismo orden siempre.
        trades.sort(key=lambda t: (t["open_time"], t["symbol"]))
        open_slots, accepted, rejected = [], [], 0
        for t in trades:
            open_slots = [ct for ct in open_slots if ct > t["open_time"]]
            if len(open_slots) >= slots:
                rejected += 1
                continue
            open_slots.append(t["close_time"])
            accepted.append(t)

        wins = [t for t in accepted if t["close_reason"] == "TP"]
        total_pnl = sum(t["pnl"] for t in accepted)

        monthly: dict[str, dict] = {}
        for t in accepted:
            key = datetime.utcfromtimestamp(t["open_time"] / 1000).strftime("%Y-%m")
            m = monthly.setdefault(key, {"trades": 0, "pnl": 0.0, "wins": 0})
            m["trades"] += 1
            m["pnl"] += t["pnl"]
            if t["close_reason"] == "TP":
                m["wins"] += 1

        return {
            "strategy_name": profile.get("name"),
            "total_signals": len(trades),
            "accepted_trades": len(accepted),
            "rejected_no_slot": rejected,
            "win_rate_pct": round(len(wins) / len(accepted) * 100, 1) if accepted else 0,
            "total_pnl_usdt": round(total_pnl, 2),
            "capital": margin * slots,
            "monthly_breakdown": {k: {"trades": v["trades"], "pnl": round(v["pnl"], 2),
                                        "win_rate_pct": round(v["wins"] / v["trades"] * 100, 1)}
                                   for k, v in sorted(monthly.items())},
            "trades": accepted,
        }

    def run_parallel(
        self,
        strategy_type: str,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        max_workers: Optional[int] = None,
    ) -> dict:
        """
        Corre la deteccion de candidatos (la parte CPU-bound, sin I/O una vez
        cargados los datos) en paralelo por lotes de simbolos, via
        ProcessPoolExecutor -- threads no ayudan aca por el GIL (SMA/slope en
        Python puro). Cada proceso abre su PROPIA conexion sqlite de solo
        lectura y su propio BacktestEngine (no se puede compartir `self`
        entre procesos, no es picklable). El capital de 3 slots se calcula
        UNA sola vez sobre el conjunto combinado de señales de todos los
        procesos -- nunca por separado, para no inflar artificialmente el
        cupo disponible.
        """
        import os as _os
        from concurrent.futures import ProcessPoolExecutor, as_completed

        n_workers = max_workers or min(_os.cpu_count() or 4, 8)
        n_workers = max(1, min(n_workers, len(symbols))) if symbols else 1
        batches = [symbols[i::n_workers] for i in range(n_workers)]
        batches = [b for b in batches if b]

        all_raw_trades = []
        done_batches = 0
        if progress_cb:
            progress_cb(0, len(symbols))

        with ProcessPoolExecutor(max_workers=len(batches)) as ex:
            futures = {
                ex.submit(_parallel_worker, strategy_type, profile, batch, start_ms, end_ms, balance, self.db_path): batch
                for batch in batches
            }
            symbols_done = 0
            for fut in as_completed(futures):
                batch = futures[fut]
                raw_trades = fut.result()
                all_raw_trades.extend(raw_trades)
                symbols_done += len(batch)
                done_batches += 1
                if progress_cb:
                    progress_cb(symbols_done, len(symbols))

        return self._capital_sim(all_raw_trades, profile)


def _parallel_worker(strategy_type: str, profile: dict, symbols: list, start_ms: int, end_ms: int,
                      balance: float, db_path: str) -> list:
    """
    Funcion de nivel de modulo (picklable, requisito de ProcessPoolExecutor)
    -- se ejecuta en un proceso hijo, arma su propio BacktestEngine y corre
    el runner correspondiente SOLO sobre su lote de simbolos, devolviendo
    las señales crudas (antes de capital_sim, que se aplica una sola vez en
    el proceso principal sobre el total combinado).
    """
    engine = BacktestEngine(db_path)
    runners = {
        "MaGeometry": engine.run_ma_geometry,
        "FVG": engine.run_fvg,
        "AdnCompression": engine.run_adn_compression,
    }
    runner = runners[strategy_type]
    result = runner(profile, symbols, start_ms, end_ms, balance=balance)
    return result["all_signals_raw"]

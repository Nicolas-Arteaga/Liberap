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
from setup_validator import validate_pre_trade  # noqa: E402
import config as agent_config  # noqa: E402
from fvg.analyzer import FvgAnalyzer  # noqa: E402
from adn_compression.analyzer import AdnCompressionAnalyzer  # noqa: E402
from orderblock.detector import find_live_pending_blocks  # noqa: E402
# level_sweep_liquidity_tp/level_sweep_poc_filter importan strategy_lab, que a
# su vez importa TOP_40_SYMBOLS de ESTE modulo -- import perezoso (dentro de
# run_order_block) para no crear un ciclo de import al cargar engine.py.
from kline_cache import get_cache  # noqa: E402 -- OFI/funding/liquidaciones (agent/data/klines.db, DB separada de binance_vision_clean.db)

# verge_agent.py configura logging a archivo con rotacion al importarse (para
# el agente EN VIVO) -- en un backtest eso genera miles de writes a disco y
# frena todo (confirmado: 2+ min para 10 candidatos en un solo simbolo). No
# se toca verge_agent.py (es el agente real); se apaga el ruido solo aca.
logging.getLogger().setLevel(logging.ERROR)
for _name in ("VergeAgent", "RiskManager"):
    logging.getLogger(_name).setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")

# 2026-08-17: has_traded_symbol_today() en produccion real (state_manager.py)
# usa datetime.now() -- hora LOCAL del host (Argentina, UTC-3), no UTC. El
# corte de "mismo dia" para el anti-churn de 1 trade/simbolo/dia estaba
# corrido 3 horas contra mi calculo en UTC puro -- se resta este offset
# antes de tomar .date() para que el limite de dia coincida con el real.
ARG_OFFSET_MS = 3 * 60 * 60 * 1000

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

# Timeout de posiciones -- FIEL a produccion (verge_agent.py:6506-6544):
#   * la antiguedad se mide en velas de 15m FIJAS (candle_seconds=900), a
#     proposito y sin importar el timeframe de la señal -- verificado en el
#     gate de confiabilidad 2026-09-05 contra 34 trades reales de timeout
#     (moda 24.0-24.2h para maxTradeDurationCandles=96);
#   * zombie_timeout SOLO cierra si el trade esta EN PERDIDA en ese momento;
#     un trade en ganancia "se deja correr" hasta TP/SL;
#   * tope duro adicional MAX_POSITION_DURATION_HOURS = 720h (30 dias).
ZOMBIE_CANDLE_MS = 15 * 60 * 1000
MAX_POSITION_DURATION_HOURS = 720


def zombie_timeout_decision(open_ms: int, now_ms: int, max_candles: int, pnl_pct_now: float):
    """-> "zombie_timeout" | "max_duration" | None. Helper puro y testeable
    (test_engine_timeout.py). No depende del timeframe de la estrategia."""
    candles_open = (now_ms - open_ms) / ZOMBIE_CANDLE_MS
    hours_open = (now_ms - open_ms) / 3_600_000
    if candles_open >= max_candles and pnl_pct_now < 0:
        return "zombie_timeout"
    if hours_open >= MAX_POSITION_DURATION_HOURS:
        return "max_duration"
    return None

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
        self._active_by_interval: dict[str, tuple] = {}  # interval -> (rows, times) del simbolo activo AHORA
        # 2026-08-16: cache PERSISTENTE por (symbol, interval), nunca se
        # invalida -- bug real encontrado por el usuario (6 horas corriendo
        # run_fvg_global sin terminar, benchmark confirmo 9ms/llamada vs
        # 0.002ms/llamada quedandose en el mismo simbolo -- 4500x). La causa
        # NO era el analisis FVG (pandas es rapido ahi), era que
        # _active_by_interval se BORRABA COMPLETO cada vez que el walk
        # cambiaba de simbolo (ej. recorriendo 420 simbolos por tick), asi
        # que reconstruia la lista de timestamps (miles de elementos, base
        # 5m + resample 15m) de cero en CADA switch, para CADA simbolo, en
        # CADA uno de los ~70.000 ticks. Cachear por simbolo de forma
        # permanente no cambia ningun resultado (mismos rows/times de
        # siempre) -- solo evita recalcular lo mismo una y otra vez.
        self._all_by_interval: dict[tuple, tuple] = {}  # (symbol, interval) -> (rows, times)

    def set_now(self, now_ms: int):
        self.now_ms = now_ms

    def set_active_symbol(self, symbol: str, intervals: tuple = ()):
        """Fija el simbolo activo durante el walk -- precalcula rows+open_times
        (resampleadas desde la base de 5m) UNA vez por intervalo relevante,
        cacheado PERMANENTEMENTE por simbolo (ver _all_by_interval arriba)."""
        self._active_symbol = symbol
        for iv in intervals:
            key = (symbol, iv)
            cached = self._all_by_interval.get(key)
            if cached is None:
                base_rows = self._load_base(symbol)
                rows = base_rows if iv == BASE_INTERVAL else self._resample(base_rows, iv)
                cached = (rows, [r[0] for r in rows])
                self._all_by_interval[key] = cached
            self._active_by_interval[iv] = cached

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

    # ── BTC klines para BTCMacroFilter (GAP 1 del gate 2026-09-05) ──────────
    # get_klines_for_nexus() de arriba devuelve [] a proposito para el tope
    # estructural de TP de ma_slope_mode. El BTCMacroFilter necesita velas
    # REALES de BTC (1m/5m/15m/1h/1d). Se sirven aca, causal (<= now_ms),
    # desde btc_klines_1m (backfill dedicado, agent/download_btc_1m.py) para
    # 1m y por resample para el resto.
    def _load_btc_1m(self) -> list:
        if not hasattr(self, "_btc1m"):
            try:
                cur = self.conn.cursor()
                cur.execute("SELECT open_time, open, high, low, close, volume FROM btc_klines_1m "
                            "WHERE symbol='BTCUSDT' ORDER BY open_time ASC")
                self._btc1m = cur.fetchall()
                self._btc1m_t = [r[0] for r in self._btc1m]
            except sqlite3.OperationalError:
                self._btc1m, self._btc1m_t = [], []
            self._btc_resampled = {}
        return self._btc1m

    def get_btc_klines(self, interval: str, limit: int) -> list:
        """Velas de BTCUSDT hasta now_ms (nunca futuro). Devuelve dicts con las
        keys que espera BTCMacroFilter: open/high/low/close/open_time."""
        base = self._load_btc_1m()
        if not base:
            return []
        if interval == "1m":
            rows = base
        else:
            step = _INTERVAL_MS.get(interval, 60000) // 60000
            key = interval
            cached = self._btc_resampled.get(key)
            if cached is None:
                bucket_ms = 60000 * step
                buckets = {}
                for r in base:
                    b = r[0] - (r[0] % bucket_ms)
                    buckets.setdefault(b, []).append(r)
                out = []
                for b in sorted(buckets):
                    g = buckets[b]
                    out.append((b, g[0][1], max(x[2] for x in g), min(x[3] for x in g),
                                g[-1][4], sum(x[5] for x in g)))
                self._btc_resampled[key] = out
                cached = out
            rows = cached
        # causal: solo velas ya cerradas a now_ms
        cut = bisect.bisect_right([r[0] for r in rows], self.now_ms - _INTERVAL_MS.get(interval, 60000))
        sl = rows[max(0, cut - limit):cut]
        return [{"open_time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
                for r in sl]


class _HistBtcShim:
    """Fetcher minimo para BTCMacroFilter: solo implementa get_klines_for_nexus,
    redirigido a HistoricalFetcher.get_btc_klines (causal)."""
    def __init__(self, fetcher: HistoricalFetcher):
        self._f = fetcher

    def get_klines_for_nexus(self, symbol: str, interval: str = "15m", limit: int = 400) -> list:
        if symbol != "BTCUSDT":
            return []
        return self._f.get_btc_klines(interval, limit)


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


def make_orderblock_agent(fetcher: HistoricalFetcher) -> VergeAgent:
    """Idem make_fvg_agent, para StrategyType=OrderBlock.
    `_build_order_block_candidate` no usa self.fetcher directamente para el
    precio de la zona (ya viene en el item), pero sí revalida con precio
    fresco -- mismo patrón que FVG/ADN."""
    agent = VergeAgent.__new__(VergeAgent)
    agent.fetcher = fetcher
    return agent


class _FundingLookup:
    """Funding real desde agent/data/klines.db::funding_rates donde hay cobertura.
    Sin cobertura -> 0 y funding_covered=False (APPROXIMATE, sin inventar dato).
    Convencion: LONG paga cuando funding_rate>0; notional ~ qty*entry.
    """
    _KDB = os.path.join(os.path.dirname(__file__), "..", "data", "klines.db")

    def __init__(self):
        self._rows = {}
        self._ok = False
        try:
            c = sqlite3.connect(f"file:{self._KDB}?mode=ro", uri=True)
            for sym, ft, fr in c.execute(
                "SELECT symbol, funding_time, funding_rate FROM funding_rates WHERE funding_time > 1000000000000"):
                self._rows.setdefault(sym, []).append((ft, fr))
            c.close()
            for s in self._rows:
                self._rows[s].sort()
            self._ok = bool(self._rows)
        except Exception:
            self._ok = False

    def paid(self, symbol, open_ms, close_ms, qty, entry, side):
        rows = self._rows.get(symbol)
        if not self._ok or not rows:
            return 0.0, False
        # cobertura: que exista al menos una marca de funding cerca de la vida del trade
        lo = bisect.bisect_right([r[0] for r in rows], open_ms)
        hi = bisect.bisect_right([r[0] for r in rows], close_ms)
        span = [r for r in rows[lo:hi]]
        # si el trade abarca >8h y no hay ninguna marca, es que no hay cobertura real
        if not span:
            near = rows[min(lo, len(rows) - 1)][0]
            if abs(near - open_ms) > 8 * 3600 * 1000:
                return 0.0, False
            return 0.0, True
        notional = qty * entry
        total = 0.0
        for _ft, fr in span:
            pay = notional * fr
            total += pay if side == 0 else -pay
        return total, True


_FUNDING_SINGLETON = None


def _get_funding_lookup():
    global _FUNDING_SINGLETON
    if _FUNDING_SINGLETON is None:
        _FUNDING_SINGLETON = _FundingLookup()
    return _FUNDING_SINGLETON


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
        self.orderblock_agent = make_orderblock_agent(self.fetcher)
        self.risk_manager = RiskManager(fetcher=self.fetcher)
        # BTCMacroFilter real (mismo codigo de produccion) sobre datos historicos
        # de BTC — GAP 1 del gate de confiabilidad 2026-09-05.
        try:
            from btc_macro_filter import BTCMacroFilter
            self.btc_filter = BTCMacroFilter(_HistBtcShim(self.fetcher))
        except Exception:
            self.btc_filter = None

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
        signal_filters: Optional[dict] = None,
        fidelity: Optional[dict] = None,
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
                                  candidate_fn, balance, progress_cb, shadow_mode,
                                  signal_filters=signal_filters, fidelity=fidelity)

    def run_ma_geometry_global(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        fidelity: Optional[dict] = None,
    ) -> dict:
        """
        PHASE 2 del gate de confiabilidad. RELOJ GLOBAL: un solo clock de 5 min
        para todos los simbolos. La diferencia clave con run_ma_geometry
        (_run_generic per-simbolo + FIFO retroactivo) es CUANDO se abre:

          _run_generic  -> abre en la PRIMERA vela en que el patron pasa vetos
                           (y despues _capital_sim decide el cupo retroactivo).
          este runner    -> el candidato queda ELEGIBLE mientras el patron siga
                           vivo (mediana ~2h, hasta 12h — medido en phase2_timeline);
                           se ABRE solo cuando hay un cupo LIBRE, admitiendo en el
                           orden de prioridad de produccion (score x mult, luego
                           orden de simbolo ~ orden de escaneo). Es exactamente el
                           mecanismo real: produccion estuvo saturada (2 cupos
                           ocupados en 97/113 entradas) y entra "cuando se libera
                           un cupo", no "cuando aparece el patron".

        fidelity: mismos hooks que _run_generic (btc_block, daily_change,
        traded_before, occupied, blackout). Sin fidelity => mismo universo/logica,
        solo cambia el timing de admision por cupo.

        PHASE 3: internamente = ma_precompute() (caro, 1 vez) + ma_slot_sim()
        (barato, repetible con perturbaciones para el Monte Carlo del gate v4).
        """
        pc = self.ma_precompute(profile, symbols, start_ms, end_ms,
                                balance=balance, fidelity=fidelity, progress_cb=progress_cb)
        if not pc["active"]:
            return self._capital_sim([], profile, symbols_used=[])
        trades = self.ma_slot_sim(pc, start_ms, end_ms, fidelity=fidelity)
        result = self._capital_sim(trades, profile, symbols_used=pc["active"])
        result["all_signals_raw"] = trades
        return result

    def ma_precompute(self, profile, symbols, start_ms, end_ms, balance=10_000.0,
                      fidelity=None, progress_cb=None):
        """PASO caro (1 sola vez). Para cada (symbol, bucket de `interval`) evalua
        el patron + TODOS los vetos slot-independientes (BTC block, daily change,
        validate_pre_trade, risk sizing) y guarda el candidato ya listo con su
        risk. El slot-sim de abajo solo hace bookkeeping."""
        import json
        params = json.loads(profile.get("patternParamsJson") or "{}")
        interval = params.get("timeframe") or "1h"
        interval_ms = _INTERVAL_MS[interval]
        fdl = fidelity or {}
        f_btc_block = bool(fdl.get("btc_block"))
        f_daily = bool(fdl.get("daily_change"))
        btcf = getattr(self, "btc_filter", None) if f_btc_block else None
        base_need = 150 * (interval_ms // BASE_MS) + 20
        s0 = start_ms - 24 * 3600 * 1000

        def _btc_blocks_long(cand, now_ms):
            if btcf is None:
                return False
            self.fetcher.set_now(now_ms)
            btcf._regime_cache = None
            btcf._flash_crash_cache = None
            if btcf.is_flash_crash():
                return True
            if int(cand.get("side", 0)) != 0:
                return False
            return btcf.get_regime() == "DUMPING"

        active, sym5m, ready = [], {}, {}
        syms = list(symbols)
        for si, symbol in enumerate(syms):
            self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, interval))
            rb, tb = self.fetcher._active_by_interval[BASE_INTERVAL]
            if len(rb) < base_need:
                continue
            active.append(symbol)
            sym5m[symbol] = (rb, tb)
            fr = {}
            b = s0 - (s0 % interval_ms)
            while b <= end_ms:
                now_ms = b + interval_ms
                self.fetcher.set_now(now_ms)
                geo = self.ma_agent._read_ma_geometry(symbol, interval=interval)
                cand = self.ma_agent._evaluate_ma_geometry_profile(profile, geo) if geo else None
                if cand:
                    if not (f_btc_block and _btc_blocks_long(cand, now_ms)):
                        px = cand.get("price_at_signal") or cand.get("current_price")
                        if px:
                            if f_daily and cand.get("historical_daily_change_pct") is None:
                                hi = bisect.bisect_right(tb, now_ms - BASE_MS)
                                if hi >= 2:
                                    lo = bisect.bisect_left(tb, tb[hi - 1] - 24 * 3600 * 1000)
                                    if lo < hi - 1 and rb[lo][4]:
                                        cand["historical_daily_change_pct"] = (rb[hi - 1][4] - rb[lo][4]) / rb[lo][4] * 100
                            v_ok, _vc, _ = validate_pre_trade(cand, px, profile=profile, btc_filter=None, btc_corr=None)
                            if v_ok:
                                self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, interval))
                                risk = self.risk_manager._calculate_position_nexus_style(symbol, cand, balance, profile)
                                if risk:
                                    fr[b] = {"risk": risk, "score": float(cand.get("confluence_score", 0) or 0)}
                b += interval_ms
            if fr:
                ready[symbol] = fr
            if progress_cb and si % 40 == 0:
                progress_cb(si, len(syms))
        if progress_cb:
            progress_cb(len(syms), len(syms))
        return {"active": active, "sym5m": sym5m, "ready": ready, "profile": profile,
                "interval_ms": interval_ms,
                "slots": int(profile.get("maxOpenPositions", 3)),
                "max_candles": int(profile.get("maxTradeDurationCandles", 16))}

    def ma_slot_sim(self, pc, start_ms, end_ms, fidelity=None,
                    seed=0, jitter_s=0.0, jitter_ticks=0, tiebreak="sym_asc", tp_first=True):
        """PASO barato y repetible. Camina el reloj global de 5 min, abre al
        liberarse un cupo. Perturbaciones (Monte Carlo del gate v4, NO se
        optimizan):
          seed          -> RNG para desempate 'shuffle' y offsets de jitter
          jitter_s      -> +-seg de ruido en open_time y en el instante de
                           liberacion del cupo (a resolucion 5m afecta cruces
                           de vela y empates)
          jitter_ticks  -> +-N velas de 5m de ruido en CUANDO un candidato
                           pasa a ser elegible (test real de la path-dependence)
          tiebreak      -> 'sym_asc' | 'sym_desc' | 'precompute' | 'shuffle'
          tp_first      -> orden de chequeo intrabar TP/SL
        """
        import random
        rng = random.Random(seed)
        active, sym5m, ready = pc["active"], pc["sym5m"], pc["ready"]
        slots, max_candles, interval_ms = pc["slots"], pc["max_candles"], pc["interval_ms"]
        fdl = fidelity or {}
        f_traded_before = fdl.get("traded_before") or {}
        f_occupied = fdl.get("occupied") or {}
        f_blackout = fdl.get("blackout") or []
        precompute_order = {s: i for i, s in enumerate(active)}

        def _in_blackout(ts):
            return any(a <= ts <= b for a, b in f_blackout)

        def _cross_occupied(symbol, ts):
            for o, c in f_occupied.get(symbol, ()):
                if o <= ts < c:
                    return True
                if o > ts:
                    break
            return False

        def _already_traded_cross(symbol, now_ms, day_iso):
            lst = f_traded_before.get(symbol)
            if not lst:
                return False
            i = bisect.bisect_left(lst, now_ms)
            for k in range(i - 1, -1, -1):
                ot = lst[k]
                if datetime.utcfromtimestamp((ot - ARG_OFFSET_MS) / 1000).date().isoformat() != day_iso:
                    break
                if ot < now_ms:
                    return True
            return False

        # offset de elegibilidad por (symbol,bucket): +-jitter_ticks velas de 5m
        elig_off = {}
        if jitter_ticks:
            for s, fr in ready.items():
                for b in fr:
                    elig_off[(s, b)] = rng.randint(-jitter_ticks, jitter_ticks) * BASE_MS

        rows0, times0 = sym5m[active[0]]
        s_idx = bisect.bisect_left(times0, start_ms - BASE_MS)
        e_idx = bisect.bisect_right(times0, end_ms)

        open_trades: dict[str, dict] = {}
        last_trade_day: dict[str, object] = {}
        all_trades = []

        for i in range(s_idx, e_idx):
            now_ms = rows0[i][0] + BASE_MS
            day_key = datetime.utcfromtimestamp((now_ms - ARG_OFFSET_MS) / 1000).date()
            day_iso = day_key.isoformat()
            bucket = now_ms - (now_ms % interval_ms)

            for symbol in list(open_trades.keys()):
                rb, tb = sym5m[symbol]
                k = bisect.bisect_right(tb, now_ms - BASE_MS) - 1
                if k < 0:
                    continue
                ot = open_trades[symbol]
                h, l, c = rb[k][2], rb[k][3], rb[k][4]
                sd = ot["side"]
                hit_tp = (l <= ot["tp"]) if sd == 1 else (h >= ot["tp"])
                hit_sl = (h >= ot["sl"]) if sd == 1 else (l <= ot["sl"])
                closed = None
                if hit_tp and hit_sl:
                    closed = ("TP", ot["tp"]) if tp_first else ("SL", ot["sl"])
                elif hit_tp:
                    closed = ("TP", ot["tp"])
                elif hit_sl:
                    closed = ("SL", ot["sl"])
                if closed:
                    cr, _px = closed
                    ct = now_ms + (rng.uniform(-jitter_s, jitter_s) * 1000 if jitter_s else 0)
                    all_trades.append({**ot, "close_reason": cr, "close_time": int(ct)})
                    del open_trades[symbol]
                    continue
                pnl_pct = ((c - ot["entry"]) / ot["entry"]) if sd == 0 else ((ot["entry"] - c) / ot["entry"])
                _to = zombie_timeout_decision(ot["open_time"], now_ms, max_candles, pnl_pct)
                if _to:
                    ct = now_ms + (rng.uniform(-jitter_s, jitter_s) * 1000 if jitter_s else 0)
                    all_trades.append({**ot, "close_reason": _to, "close_time": int(ct),
                                        "_zombie_close_price": c})
                    del open_trades[symbol]

            free = slots - len(open_trades)
            if free <= 0 or (f_blackout and _in_blackout(now_ms)):
                continue

            eligible = []
            for symbol, fr in ready.items():
                entry = fr.get(bucket)
                if entry is None:
                    if jitter_ticks:
                        # con jitter, un fire de un bucket vecino puede volverse elegible
                        alt = fr.get(bucket - interval_ms) or fr.get(bucket + interval_ms)
                        if alt is None:
                            continue
                        off = elig_off.get((symbol, bucket - interval_ms), 0) or elig_off.get((symbol, bucket + interval_ms), 0)
                        if not (bucket - interval_ms + interval_ms + off <= now_ms <= bucket + interval_ms + off):
                            continue
                        entry = alt
                    else:
                        continue
                elif jitter_ticks:
                    off = elig_off.get((symbol, bucket), 0)
                    if now_ms < bucket + interval_ms + off:
                        continue
                if symbol in open_trades or last_trade_day.get(symbol) == day_key:
                    continue
                if f_traded_before and _already_traded_cross(symbol, now_ms, day_iso):
                    continue
                if f_occupied and _cross_occupied(symbol, now_ms):
                    continue
                eligible.append((entry["score"], symbol, entry["risk"]))

            if not eligible:
                continue
            if tiebreak == "shuffle":
                rng.shuffle(eligible)
                eligible.sort(key=lambda e: -e[0])
            elif tiebreak == "sym_desc":
                eligible.sort(key=lambda e: (-e[0], e[1]), reverse=False)
                eligible.sort(key=lambda e: e[1], reverse=True)
                eligible.sort(key=lambda e: -e[0])
            elif tiebreak == "precompute":
                eligible.sort(key=lambda e: (-e[0], precompute_order.get(e[1], 0)))
            else:  # sym_asc
                eligible.sort(key=lambda e: (-e[0], e[1]))
            for _sc, symbol, risk in eligible[:free]:
                ot_ms = now_ms + (int(rng.uniform(-jitter_s, jitter_s) * 1000) if jitter_s else 0)
                open_trades[symbol] = {
                    "symbol": symbol, "side": risk["side"], "open_time": ot_ms,
                    "entry": risk["entry_price"], "sl": risk["sl_price"], "tp": risk["tp_price"],
                    "margin": risk["margin"],
                }
                last_trade_day[symbol] = day_key

        return all_trades

    def run_fvg(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        shadow_mode: bool = False,
        signal_filters: Optional[dict] = None,
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
                                  candidate_fn, balance, progress_cb, shadow_mode,
                                  signal_filters=signal_filters)

    def run_order_block(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        shadow_mode: bool = False,
        signal_filters: Optional[dict] = None,
    ) -> dict:
        """
        StrategyType=OrderBlock. Detección real de detector.py (swing/BOS/
        mitigación, plain-list, sin pandas -- misma función que usa
        python-service/orderblock/analyzer.py para el vivo, solo que acá se
        llama directo en vez de a través del wrapper pandas, por costo: el
        wrapper completo tardaba >6s/símbolo/vela en el walk de 5m). TP de
        liquidez y filtro POC/HVN reusan las MISMAS funciones plain-list ya
        validadas 1:1 contra el original de FVG (level_sweep_liquidity_tp.py/
        level_sweep_poc_filter.py) + verge_agent.py::
        _build_order_block_candidate para el candidato (SL/TP estructural) --
        solo bearish/SHORT (única dirección validada, ver PROGRESS_LOG
        2026-08-22).
        """
        import json
        from level_sweep_liquidity_tp import liquidity_tp as _ob_liquidity_tp
        from level_sweep_poc_filter import hvn_bins as _ob_hvn_bins, dist_to_nearest_hvn_pct as _ob_dist_to_hvn

        params = json.loads(profile.get("patternParamsJson") or "{}")
        interval = params.get("timeframe") or "15m"
        interval_ms = _INTERVAL_MS[interval]
        require_poc = params.get("requirePoc", True)

        # Cache por bucket de vela -- la zona OB (swing/BOS/mitigación) no
        # puede cambiar dentro de la misma vela de `interval`, así que
        # recalcularla en cada tick de 5m (walk base de _run_generic) sería
        # 3-12x trabajo redundante. Mismo razonamiento que scan_step_ticks
        # en run_fvg_global, aplicado acá como cache simple por símbolo.
        _cache: dict[str, tuple] = {}  # symbol -> (bucket_ms, candidate|None)

        def candidate_fn(symbol):
            now_ms = self.fetcher.now_ms
            bucket = now_ms - (now_ms % interval_ms)
            cached = _cache.get(symbol)
            if cached is not None and cached[0] == bucket:
                return cached[1]

            candidate = None
            try:
                rows = self.fetcher.get_klines_with_partial(symbol, interval, 300)
                if len(rows) >= 100:
                    opens = [r[1] for r in rows]
                    highs = [r[2] for r in rows]
                    lows = [r[3] for r in rows]
                    closes = [r[4] for r in rows]
                    vols = [r[5] for r in rows]
                    times = [r[0] for r in rows]
                    pending = find_live_pending_blocks(opens, highs, lows, closes, times)
                    ob = pending.get("bearish")
                    if ob is not None:
                        current_price = closes[-1]
                        top, bottom = ob["ob_top"], ob["ob_bottom"]
                        if bottom <= current_price <= top:
                            entry_status, dist_pct = "IN_ZONE", 0.0
                        else:
                            dist_pct = abs(current_price - top) / current_price * 100.0 if current_price else 999.0
                            entry_status = "APPROACHING" if dist_pct <= 0.5 else "FAR"
                        if entry_status in ("IN_ZONE", "APPROACHING"):
                            entry_price = top  # borde de mitigación real (SHORT)
                            tp_price = _ob_liquidity_tp(closes, highs, lows, len(rows) - 1, 1, entry_price)
                            if tp_price is not None and tp_price < entry_price:
                                poc_ok = True
                                if require_poc:
                                    start = max(0, len(rows) - 1 - 200)
                                    hvns, _ = _ob_hvn_bins(highs[start:], lows[start:], vols[start:])
                                    poc_ok = _ob_dist_to_hvn(entry_price, hvns) <= 0.5
                                if poc_ok:
                                    gap = top - bottom
                                    sl_price = top + gap * 0.15
                                    item = {
                                        "symbol": symbol, "direction": "bearish",
                                        "current_price": current_price,
                                        "sl_price": sl_price, "tp_price": tp_price,
                                        "tp_distance_pct": abs(tp_price - current_price) / current_price * 100.0,
                                        "confluence_score": 70.0 if entry_status == "IN_ZONE" else 55.0,
                                        "entry_status": entry_status, "poc_confluence": poc_ok,
                                    }
                                    candidate = self.orderblock_agent._build_order_block_candidate(item, profile)
            except Exception:
                candidate = None

            _cache[symbol] = (bucket, candidate)
            return candidate

        return self._run_generic(profile, symbols, start_ms, end_ms, interval,
                                  candidate_fn, balance, progress_cb, shadow_mode,
                                  signal_filters=signal_filters)

    @staticmethod
    def _passes_signal_filters(cache, symbol: str, now_ms: int, candidate: dict, sf: dict) -> bool:
        """
        Replica exacta de los vetoes opt-in de setup_validator.py (funding
        extremo, cascada de liquidaciones -- secciones 2 y 3 del epic
        market-data-expansion) mas un filtro de OFI direccional nuevo
        (seccion 1, todavia sin veto de produccion -- es justamente lo que
        este A/B decide si vale la pena agregar). Point-in-time (now_ms),
        nunca time.time() -- sin lookahead, mismo principio que el resto del
        motor. Side: 0=LONG, 1=SHORT (igual que risk_manager/candidate).
        """
        side = int(candidate.get("side", 0))

        ofi_cfg = sf.get("ofi_direction") or {}
        if ofi_cfg.get("enabled"):
            ofi = cache.get_ofi_before(symbol, now_ms)
            if ofi is not None:
                min_abs = float(ofi_cfg.get("min_abs_ofi", 0.1))
                # OFI > 0 = presion compradora (mas volumen en el bid) -> favorece LONG.
                # OFI < 0 = presion vendedora -> favorece SHORT. Igual que produccion
                # nunca vetea por "neutral" (|ofi| < min_abs), solo por señal clara
                # en contra de la direccion del candidato.
                if side == 0 and ofi < -min_abs:
                    return False
                if side == 1 and ofi > min_abs:
                    return False
            # ofi is None (sin cobertura en ese punto) -> fail-open.

        funding_cfg = sf.get("funding_extreme") or {}
        if funding_cfg.get("enabled"):
            funding_rate = cache.get_funding_before(symbol, now_ms)
            if funding_rate is not None:
                funding_pct = funding_rate * 100.0
                max_abs = float(funding_cfg.get("max_abs_funding_pct", 0.05))
                if side == 0 and funding_pct > max_abs:
                    return False
                if side == 1 and funding_pct < -max_abs:
                    return False
            # funding_rate is None -> fail-open, igual que produccion.

        liq_cfg = sf.get("liquidation_cascade") or {}
        if liq_cfg.get("enabled"):
            cascade = cache.get_liquidation_cascade(
                symbol,
                recent_minutes=int(liq_cfg.get("recent_minutes", 15)),
                baseline_hours=int(liq_cfg.get("baseline_hours", 4)),
                threshold_multiplier=float(liq_cfg.get("threshold_multiplier", 3.0)),
                at_timestamp_ms=now_ms,
            )
            if cascade is not None and cascade.get("cascade_side"):
                risky_side = 1 if cascade["cascade_side"] == "Sell" else 0
                if side == risky_side:
                    return False
            # cascade is None (sin cobertura) -> fail-open, igual que produccion.

        return True

    def run_adn_compression(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        shadow_mode: bool = False,
        signal_filters: Optional[dict] = None,
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
                                  candidate_fn, balance, progress_cb, shadow_mode,
                                  signal_filters=signal_filters)

    def run_fvg_global(
        self,
        profile: dict,
        symbols: list,
        start_ms: int,
        end_ms: int,
        balance: float = 10_000.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        scan_step_ticks: int = 1,
        checkpoint_path: Optional[str] = None,
        checkpoint_every: int = 2000,
        fidelity: Optional[dict] = None,
    ) -> dict:
        """
        StrategyType=FVG, version FIEL a produccion -- root cause real
        2026-08-09: run_fvg/_run_generic caminan cada simbolo AISLADO en su
        propia linea de tiempo, sin competencia entre simbolos. Produccion
        real (python-service/fvg/analyzer.py::scan, linea 419-459) hace lo
        OPUESTO: en cada ciclo de 5 min escanea TODO el watchlist de una,
        ordena por tp_distance_pct y se queda con el TOP 5 -- el resto de
        los simbolos, aunque tengan zona valida, se descarta ese ciclo sin
        intentar abrir nada. Confirmado con datos reales: para el mismo dia
        (12/7/2026) run_fvg genero 24 trades en simbolos que NO coinciden
        NI UNO con los 10 trades reales que el agente ejecuto ese dia --
        no era un problema de PnL, eran candidatos completamente distintos.

        Esta version camina el tiempo GLOBALMENTE (un solo reloj de 5 min
        para todos los simbolos, no un walk por simbolo), en cada paso
        escanea todos los simbolos vivos, aplica el mismo corte top-5 por
        tp_distance_pct, y solo ahi intenta abrir (respetando por simbolo
        el mismo criterio de _run_generic: no re-entrar si ya hay una
        posicion abierta en ese simbolo, ni mas de 1 intento por dia).

        2026-08-16: `scan_step_ticks` (default 1 = fiel a produccion exacta)
        separa el chequeo de TP/SL de posiciones abiertas (barato, SIEMPRE
        cada 5 min via BASE_INTERVAL -- ahi esta la fidelidad real de
        cuando cierra un trade) del escaneo de NUEVAS señales FVG (caro,
        llama al analyzer real con pandas) -- la zona FVG de un simbolo no
        puede cambiar dentro de la misma vela de 15m de todos modos, asi
        que escanearla cada 5 min es 3x trabajo redundante para 2 de cada 3
        ticks. Con scan_step_ticks=3 se escanean candidatos nuevos solo
        cada 15 min reales (perdiendo unicamente precision del PRECIO de
        entrada dentro de esa ventana de 15 min, no la deteccion de la
        zona en si), sin tocar la fidelidad de cuando cierra cada trade.
        `checkpoint_path`: si se pasa, vuelca `all_trades` a ese archivo
        cada `checkpoint_every` ticks -- root cause real 2026-08-16: una
        corrida de 6+ horas se mato sin resultado parcial recuperable.
        """
        import json
        params = json.loads(profile.get("patternParamsJson") or "{}")
        interval = params.get("timeframe") or "15m"
        allow_long = profile.get("allowLong", True)
        allow_short = profile.get("allowShort", True)

        # ── fidelity (Phase 3): mismos hooks que _run_generic/ma_slot_sim ──
        fdl = fidelity or {}
        _fg_btc = bool(fdl.get("btc_block"))
        _fg_daily = bool(fdl.get("daily_change"))
        _fg_tb = fdl.get("traded_before") or {}
        _fg_occ = fdl.get("occupied") or {}
        _fg_btcf = getattr(self, "btc_filter", None) if _fg_btc else None

        def _fg_btc_blocks(cand):
            if _fg_btcf is None:
                return False
            _fg_btcf._regime_cache = None
            _fg_btcf._flash_crash_cache = None
            if _fg_btcf.is_flash_crash():
                return True
            if int(cand.get("side", 0)) != 0:
                return False
            return _fg_btcf.get_regime() == "DUMPING"

        def _fg_traded(symbol, now_ms, day_iso):
            lst = _fg_tb.get(symbol)
            if not lst:
                return False
            i = bisect.bisect_left(lst, now_ms)
            for k in range(i - 1, -1, -1):
                ot = lst[k]
                if datetime.utcfromtimestamp((ot - ARG_OFFSET_MS) / 1000).date().isoformat() != day_iso:
                    break
                if ot < now_ms:
                    return True
            return False

        def _fg_occupied(symbol, ts):
            for o, c in _fg_occ.get(symbol, ()):
                if o <= ts < c:
                    return True
                if o > ts:
                    break
            return False

        # Precalienta cache de klines de cada simbolo (evita miles de misses
        # de sqlite entreverados con el loop de escaneo).
        active_symbols = []
        for symbol in symbols:
            self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, interval))
            rows_base, _ = self.fetcher._active_by_interval[BASE_INTERVAL]
            if len(rows_base) >= 150 * (_INTERVAL_MS[interval] // BASE_MS) + 20:
                active_symbols.append(symbol)

        open_trades: dict[str, dict] = {}   # symbol -> trade abierto
        last_trade_day: dict[str, object] = {}
        all_trades = []

        # Reloj global: todos los timestamps de 5m dentro del rango, tomados
        # del primer simbolo activo (todos comparten la misma grilla de 5m).
        self.fetcher.set_active_symbol(active_symbols[0], intervals=(BASE_INTERVAL,))
        rows0, times0 = self.fetcher._active_by_interval[BASE_INTERVAL]
        start_idx = bisect.bisect_left(times0, start_ms - BASE_MS)
        end_idx = bisect.bisect_right(times0, end_ms)
        total_ticks = max(0, end_idx - start_idx)

        for tick_n, i in enumerate(range(start_idx, end_idx)):
          try:
            now_ms = rows0[i][0] + BASE_MS
            self.fetcher.set_now(now_ms)

            # ── Paso 1: TP/SL de posiciones abiertas -- SIEMPRE cada 5 min,
            # nunca se saltea (aca vive la fidelidad real de cuando cierra
            # un trade, independiente de scan_step_ticks). ──
            for symbol in list(open_trades.keys()):
                self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL,))
                ot = open_trades[symbol]
                rows, times = self.fetcher._active_by_interval[BASE_INTERVAL]
                idx_now = bisect.bisect_right(times, now_ms - BASE_MS) - 1
                if idx_now < 0:
                    continue
                h, l, c = rows[idx_now][2], rows[idx_now][3], rows[idx_now][4]
                side = ot["side"]
                hit_tp = (l <= ot["tp"]) if side == 1 else (h >= ot["tp"])
                hit_sl = (h >= ot["sl"]) if side == 1 else (l <= ot["sl"])
                if hit_tp:
                    all_trades.append({**ot, "close_reason": "TP", "close_time": now_ms})
                    del open_trades[symbol]
                elif hit_sl:
                    all_trades.append({**ot, "close_reason": "SL", "close_time": now_ms})
                    del open_trades[symbol]
                else:
                    # FIEL a produccion -- ver zombie_timeout_decision.
                    max_candles = int(profile.get("maxTradeDurationCandles", 16))
                    pnl_pct_now = ((c - ot["entry"]) / ot["entry"]) if ot["side"] == 0 \
                        else ((ot["entry"] - c) / ot["entry"])
                    _to = zombie_timeout_decision(ot["open_time"], now_ms, max_candles, pnl_pct_now)
                    if _to:
                        all_trades.append({**ot, "close_reason": _to,
                                            "close_time": now_ms, "_zombie_close_price": c})
                        del open_trades[symbol]

            # ── Paso 2: escaneo de candidatos NUEVOS -- caro (analyzer real
            # con pandas), solo cada scan_step_ticks (la zona FVG de un
            # simbolo no puede cambiar dentro de la misma vela de 15m). ──
            if tick_n % scan_step_ticks == 0:
                raw_candidates = []  # (tp_distance_pct, symbol, item)
                for symbol in active_symbols:
                    if symbol in open_trades:
                        continue  # ya tiene posicion, no compite por top-5

                    day_key = datetime.utcfromtimestamp((now_ms - ARG_OFFSET_MS) / 1000).date()
                    if last_trade_day.get(symbol) == day_key:
                        continue
                    if _fg_tb and _fg_traded(symbol, now_ms, day_key.isoformat()):
                        continue
                    if _fg_occ and _fg_occupied(symbol, now_ms):
                        continue

                    self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, interval))
                    try:
                        item, _reason = self.fvg_analyzer._scan_symbol(symbol, interval, sort_by="range")
                    except Exception:
                        continue
                    if not item:
                        continue
                    if item.direction == "bullish" and not allow_long:
                        continue
                    if item.direction == "bearish" and not allow_short:
                        continue
                    raw_candidates.append((item.tp_distance_pct, symbol, item))

                # ── Corte real: top 5 por tp_distance_pct de TODO el universo ──
                raw_candidates.sort(key=lambda x: x[0], reverse=True)
                for _tp_dist, symbol, item in raw_candidates[:5]:
                    item_dict = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    candidate = self.fvg_agent._build_fvg_candidate(item_dict, profile)
                    if not candidate:
                        continue

                    # fidelity Phase 3: BTC block + historical_daily_change
                    self.fetcher.set_now(now_ms)
                    self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, interval))
                    if _fg_btc and _fg_btc_blocks(candidate):
                        continue
                    if _fg_daily and candidate.get("historical_daily_change_pct") is None:
                        _rb, _tb = self.fetcher._active_by_interval[BASE_INTERVAL]
                        _hi = bisect.bisect_right(_tb, now_ms - BASE_MS)
                        if _hi >= 2:
                            _lo = bisect.bisect_left(_tb, _tb[_hi - 1] - 24 * 3600 * 1000)
                            if _lo < _hi - 1 and _rb[_lo][4]:
                                candidate["historical_daily_change_pct"] = (_rb[_hi - 1][4] - _rb[_lo][4]) / _rb[_lo][4] * 100

                    # 2026-08-17: root cause real de la calibracion fallida
                    # (motor daba -$60.94, produccion real dio ~+$150 en el
                    # mismo mes) -- validate_pre_trade() NUNCA se llamaba en
                    # este motor. Produccion real filtra CADA candidato de
                    # FVG por el stack completo de vetos (#1,#3-#9 +
                    # funding/liquidacion/confluence_ceiling/etc, ver
                    # verge_agent.py:_run_fvg_scan linea ~1449) antes de
                    # abrir -- el backtest abria TODOS los candidatos del
                    # top-5 sin filtrar nada. btc_filter/btc_corr quedan en
                    # None (degradacion conocida: BTCMacroFilter necesita
                    # velas de 1m que la DB historica no tiene) -- el resto
                    # del stack de vetos (RSI extremo, distancia a MA7,
                    # señal stale, MinConfluenceScore, rango minimo,
                    # funding extremo, SL carisimo, etc.) se aplica igual
                    # que en produccion.
                    v_ok, _v_code, _ = validate_pre_trade(
                        candidate, candidate["price_at_signal"], profile=profile, btc_filter=None, btc_corr=None
                    )
                    if not v_ok:
                        continue

                    self.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, interval))
                    risk = self.risk_manager._calculate_position_nexus_style(symbol, candidate, balance, profile)
                    if not risk:
                        continue
                    open_trades[symbol] = {
                        "symbol": symbol, "side": risk["side"], "open_time": now_ms,
                        "entry": risk["entry_price"], "sl": risk["sl_price"], "tp": risk["tp_price"],
                        "margin": risk["margin"],
                    }
                    day_key = datetime.utcfromtimestamp((now_ms - ARG_OFFSET_MS) / 1000).date()
                    last_trade_day[symbol] = day_key

            if progress_cb and tick_n % 500 == 0:
                progress_cb(tick_n, total_ticks)
            if checkpoint_path and tick_n % checkpoint_every == 0 and tick_n > 0:
                try:
                    with open(checkpoint_path, "w", encoding="utf-8") as f:
                        json.dump({"tick_n": tick_n, "total_ticks": total_ticks, "all_trades": all_trades}, f)
                except OSError:
                    pass
          except Exception as e:
            logger.error(f"[FVG-GLOBAL] error en tick {tick_n} ({now_ms}): {type(e).__name__}: {e}")
            continue

        if progress_cb:
            progress_cb(total_ticks, total_ticks)
        if checkpoint_path:
            try:
                with open(checkpoint_path, "w", encoding="utf-8") as f:
                    json.dump({"tick_n": total_ticks, "total_ticks": total_ticks, "all_trades": all_trades}, f)
            except OSError:
                pass

        result = self._capital_sim(all_trades, profile, symbols_used=active_symbols)
        result["all_signals_raw"] = all_trades
        return result

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
        signal_filters: Optional[dict] = None,
        fidelity: Optional[dict] = None,
    ) -> dict:
        """
        Motor de caminata GENERICO -- cualquier StrategyType lo puede usar
        con solo pasarle su propio `candidate_fn(symbol) -> candidato|None`
        (la deteccion de patron especifica de esa estrategia). El resto
        (avance cada 5 min, TP/SL, zombie_timeout, capital limitado,
        shadow_mode) es igual para todas -- ya validado 1:1 contra trades
        reales con MaGeometry (ver PROGRESS_LOG 2026-07-26).

        signal_filters (opt-in, epic market-data-expansion #156, tareas
        1.7/2.6/3.6): dict opcional para el A/B de señales de order
        flow/funding/liquidaciones sin tocar produccion. Mismos vetoes que
        setup_validator.py (funding_extreme_*, liquidation_cascade_same_
        direction) mas un filtro direccional de OFI nuevo (todavia no existe
        en produccion, es lo que este A/B evalua si vale la pena agregar).
        Sin cobertura de dato para ese symbol/momento -> fail-open, mismo
        criterio que produccion (nunca bloquear por falta de un dato
        opcional). Shape:
          {"ofi_direction": {"enabled": True, "min_abs_ofi": 0.1},
           "funding_extreme": {"enabled": True, "max_abs_funding_pct": 0.05},
           "liquidation_cascade": {"enabled": True, "recent_minutes": 15,
                                    "baseline_hours": 4, "threshold_multiplier": 3.0}}
        """
        sf = signal_filters or {}
        cache = get_cache() if sf else None
        interval_ms = _INTERVAL_MS[interval]
        min_candles = 150
        min_base_needed = min_candles * (interval_ms // BASE_MS)

        # ── fidelity (gate de confiabilidad 2026-09-05) ──────────────────────
        # dict opcional para acercar el replay a la logica real del agente:
        #   btc_block   : bool   -> replica "BTC INTELLIGENT BLOCKING" (LONG
        #                           bloqueado si BTCMacroFilter.get_regime()=="DUMPING"
        #                           sin desacople) + pausa por flash crash.
        #   daily_change: bool   -> inyecta candidate["historical_daily_change_pct"]
        #                           (cambio 24h real hasta now_ms) para que el veto
        #                           daily_pump/dump de validate_pre_trade NO pegue a
        #                           la API en vivo (bug real, setup_validator.py:1199).
        #   traded_before : dict[symbol -> sorted list[opened_ms]] -> reconstruye
        #                           has_traded_symbol_today CRUZADO entre estrategias
        #                           a partir de trades reales (no un modelo): un
        #                           candidato se descarta si CUALQUIER estrategia ya
        #                           abrio ese simbolo antes de now_ms en el mismo dia
        #                           local (Argentina), igual que _should_skip().
        #   blackout : list[(start_ms,end_ms)] -> ventanas en que el agente real
        #                           estuvo detenido (flash-crash pause, downtime).
        fdl = fidelity or {}
        f_btc_block = bool(fdl.get("btc_block"))
        f_daily = bool(fdl.get("daily_change"))
        f_traded_before = fdl.get("traded_before") or {}
        f_blackout = fdl.get("blackout") or []
        f_occupied = fdl.get("occupied") or {}

        def _already_traded_cross_strategy(symbol, now_ms, day_iso):
            lst = f_traded_before.get(symbol)
            if not lst:
                return False
            i = bisect.bisect_left(lst, now_ms)
            for k in range(i - 1, -1, -1):
                ot = lst[k]
                d = datetime.utcfromtimestamp((ot - ARG_OFFSET_MS) / 1000).date().isoformat()
                if d != day_iso:
                    break
                if ot < now_ms:
                    return True
            return False

        def _cross_occupied(symbol, ts):
            for o, c in f_occupied.get(symbol, ()):
                if o <= ts < c:
                    return True
                if o > ts:
                    break
            return False
        btcf = getattr(self, "btc_filter", None) if f_btc_block else None

        def _in_blackout(ts):
            for a, b in f_blackout:
                if a <= ts <= b:
                    return True
            return False

        def _btc_blocks_long(cand, ts):
            """Replica verge_agent.py:6249-6284 (Capa C) + flash-crash pause."""
            if btcf is None:
                return False
            btcf._regime_cache = None
            btcf._flash_crash_cache = None
            if btcf.is_flash_crash():
                return True
            if int(cand.get("side", 0)) != 0:
                return False
            if btcf.get_regime() != "DUMPING":
                return False
            # desacople institucional real -- para inyeccion directa (MA/FVG) los
            # campos volume_ratio/cvd_delta no vienen de Nexus => casi siempre False,
            # igual que en produccion.
            feats = cand.get("agent_audit_context", {}).get("nexus15", {}).get("features", {})
            vr = cand.get("volume_ratio") or feats.get("volume_ratio_20", 0)
            cvd = cand.get("cvd_delta") or feats.get("cvd_delta", 0)
            nx = float(cand.get("nexus_confidence", 0) or cand.get("confluence_score", 0) or 0)
            try:
                import config as _ac
                decouple = (vr > _ac.BTC_DECOUPLE_MIN_VOLUME_RATIO and cvd > 0
                            and nx >= _ac.BTC_DECOUPLE_MIN_NEXUS)
            except Exception:
                decouple = False
            return not decouple

        def _hist_daily_change(symbol, ts):
            """cambio % de las ultimas 24h de `symbol` hasta ts (base 5m, causal)."""
            rows, times = self.fetcher._active_by_interval.get(BASE_INTERVAL, (None, None))
            if not rows:
                return None
            hi = bisect.bisect_right(times, ts - BASE_MS)
            if hi < 2:
                return None
            lo = bisect.bisect_left(times, times[hi - 1] - 24 * 3600 * 1000)
            if lo >= hi - 1:
                return None
            p0 = rows[lo][4]
            p1 = rows[hi - 1][4]
            return ((p1 - p0) / p0 * 100.0) if p0 else None

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
                        # zombie_timeout -- FIEL a produccion (ver zombie_timeout_decision
                        # y su nota; verificado en el gate de confiabilidad 2026-09-05).
                        max_candles = int(profile.get("maxTradeDurationCandles", 16))
                        pnl_pct_now = ((c - open_trade["entry"]) / open_trade["entry"]) if side == 0 \
                            else ((open_trade["entry"] - c) / open_trade["entry"])
                        _to = zombie_timeout_decision(open_trade["open_time"], now_ms, max_candles, pnl_pct_now)
                        if _to:
                            all_trades.append({**open_trade, "close_reason": _to,
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

                day_key = datetime.utcfromtimestamp((now_ms - ARG_OFFSET_MS) / 1000).date()
                if last_trade_day == day_key:
                    j += 1
                    continue

                # has_traded_symbol_today CRUZADO entre estrategias (fidelity)
                if f_traded_before and _already_traded_cross_strategy(symbol, now_ms, day_key.isoformat()):
                    j += 1
                    continue
                if f_occupied and _cross_occupied(symbol, now_ms):
                    j += 1
                    continue

                # agente detenido (flash-crash pause / downtime real)
                if f_blackout and _in_blackout(now_ms):
                    j += 1
                    continue

                candidate = candidate_fn(symbol)
                if not candidate:
                    j += 1
                    continue

                if sf and not self._passes_signal_filters(cache, symbol, now_ms, candidate, sf):
                    j += 1
                    continue

                # BTC INTELLIGENT BLOCKING (Capa C) + flash-crash pause -- GAP 1
                if f_btc_block and _btc_blocks_long(candidate, now_ms):
                    j += 1
                    continue

                # historical_daily_change_pct -- evita que el veto daily_pump/dump
                # de validate_pre_trade pegue a la API de Binance en vivo (bug real).
                if f_daily and candidate.get("historical_daily_change_pct") is None:
                    dch = _hist_daily_change(symbol, now_ms)
                    if dch is not None:
                        candidate["historical_daily_change_pct"] = dch

                # Produccion real filtra CADA candidato por el stack completo de
                # vetos antes de abrir.
                price_at_signal = candidate.get("price_at_signal") or candidate.get("current_price")
                if price_at_signal:
                    v_ok, _v_code, _ = validate_pre_trade(
                        candidate, price_at_signal, profile=profile, btc_filter=None, btc_corr=None
                    )
                    if not v_ok:
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

        result = self._capital_sim(all_trades, profile, symbols_used=symbols)
        result["all_signals_raw"] = all_trades
        result["shadow_signals"] = shadow_signals
        return result

    def _capital_sim(self, trades: list, profile: dict, symbols_used: Optional[list] = None,
                     fee_per_side: Optional[float] = None, model_funding: bool = True,
                     tiebreak: str = "sym_asc", seed: int = 0) -> dict:
        margin = float(profile.get("marginPerTrade", 150))
        slots = int(profile.get("maxOpenPositions", 3))
        fee = FEE_PER_SIDE if fee_per_side is None else fee_per_side

        fund_cache = _get_funding_lookup() if model_funding else None
        for t in trades:
            qty = margin / t["entry"]
            if t["close_reason"] == "TP":
                close_px = t["tp"]
            elif t["close_reason"] in ("zombie_timeout", "max_duration"):
                close_px = t["_zombie_close_price"]
            else:
                close_px = t["sl"]
            gross = qty * (close_px - t["entry"]) if t["side"] == 0 else qty * (t["entry"] - close_px)
            fees = (qty * t["entry"] + qty * close_px) * fee
            # funding: real donde hay cobertura en funding_rates (klines.db),
            # 0 + flag donde no la hay (APPROXIMATE, ver el reporte de repair).
            if fund_cache is not None:
                fund_usd, fund_cov = fund_cache.paid(t["symbol"], t["open_time"], t["close_time"],
                                                     qty, t["entry"], t["side"])
            else:
                fund_usd, fund_cov = 0.0, False
            t["funding"] = fund_usd
            t["funding_covered"] = fund_cov
            t["_fees"] = fees
            t["pnl"] = gross - fees - fund_usd

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
        if tiebreak == "shuffle":
            import random as _r
            _rng = _r.Random(seed)
            _rng.shuffle(trades)
            trades.sort(key=lambda t: t["open_time"])          # estable -> empates aleatorios
        elif tiebreak == "sym_desc":
            trades.sort(key=lambda t: (t["open_time"], t["symbol"]), reverse=False)
            trades.sort(key=lambda t: t["symbol"], reverse=True)
            trades.sort(key=lambda t: t["open_time"])
        else:  # sym_asc (default historico)
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
            "symbols_used": sorted(symbols_used) if symbols_used else None,
            "symbols_count": len(symbols_used) if symbols_used else None,
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
        fidelity: Optional[dict] = None,
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
        import multiprocessing
        import queue as _queue
        from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

        n_workers = max_workers or min(_os.cpu_count() or 4, 8)
        n_workers = max(1, min(n_workers, len(symbols))) if symbols else 1
        batches = [symbols[i::n_workers] for i in range(n_workers)]
        batches = [b for b in batches if b]

        total_symbols = len(symbols)
        if progress_cb:
            progress_cb(0, total_symbols)

        # Progreso granular real (por simbolo, no por lote entero) -- bug
        # real 2026-07-26: con progreso por lote, la barra quedaba en 0%
        # durante minutos hasta que el PRIMER lote completo terminaba,
        # aunque el trabajo ya estuviera avanzando de verdad adentro de cada
        # proceso. Cada worker reporta 1 mensaje por simbolo terminado a
        # esta cola compartida (multiprocessing.Manager, picklable entre
        # procesos); el proceso principal la drena sin bloquear mientras
        # espera que terminen los futures.
        manager = multiprocessing.Manager()
        progress_queue = manager.Queue()

        all_raw_trades = []
        done_count = 0

        with ProcessPoolExecutor(max_workers=len(batches)) as ex:
            futures = {
                ex.submit(_parallel_worker, strategy_type, profile, batch, start_ms, end_ms, balance,
                          self.db_path, progress_queue, fidelity): batch
                for batch in batches
            }
            pending = set(futures.keys())
            while pending:
                drained = 0
                while True:
                    try:
                        progress_queue.get_nowait()
                        drained += 1
                    except _queue.Empty:
                        break
                if drained and progress_cb:
                    done_count = min(done_count + drained, total_symbols)
                    progress_cb(done_count, total_symbols)

                done_now, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for fut in done_now:
                    all_raw_trades.extend(fut.result())

        if progress_cb:
            progress_cb(total_symbols, total_symbols)

        return self._capital_sim(all_raw_trades, profile, symbols_used=symbols)


def _parallel_worker(strategy_type: str, profile: dict, symbols: list, start_ms: int, end_ms: int,
                      balance: float, db_path: str, progress_queue=None, fidelity=None) -> list:
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
        "OrderBlock": engine.run_order_block,
    }
    runner = runners[strategy_type]

    def _report_progress(done, total):
        if progress_queue is not None:
            progress_queue.put(1)  # 1 simbolo mas terminado en ESTE lote

    kw = {"balance": balance, "progress_cb": _report_progress}
    if strategy_type == "MaGeometry" and fidelity is not None:
        kw["fidelity"] = fidelity
    result = runner(profile, symbols, start_ms, end_ms, **kw)
    return result["all_signals_raw"]

import requests
from datetime import datetime, timezone
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .schemas import AdnCompressionScanRequest, AdnCompressionScanResponse, AdnCompressionItem
from shared_kline_cache import get_or_fetch
import logging

logger = logging.getLogger("ADN_COMPRESSION")

# ── Umbrales del patrón (calibrados a ojo por Nico sobre casos reales de
# TUSDT en 5m y 1D — mismo patrón fractal en ambas temporalidades) ──────────
MAX_SPREAD_PCT = 1.2          # MA25/50/99 se consideran "agrupadas" si su spread es <= esto (% del precio)
MIN_COMPRESSION_CANDLES = 6   # duración mínima de la compresión para que cuente como real, no ruido
MIN_ADN_CROSSINGS = 2         # cruces mínimos de MA7 contra el paquete para confirmar el "ADN"
SEARCH_LOOKBACK = 60          # ventana hacia atrás (en velas) donde se busca la compresión más reciente
IGNITION_MULTIPLIER_THRESHOLD = 3.0  # una vela >= 3x el rango promedio de la compresión = ignición
PULLBACK_TOLERANCE_PCT = 1.0  # distancia a MA7 para considerar que el precio está "respirando" ahí

_PHASE_PRIORITY = {"PULLBACK_TO_MA7": 3, "COILED": 2, "EXTENDED": 1, "EXHAUSTED": 0}


def _sma(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, len(values)):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


class AdnCompressionAnalyzer:
    """
    🧬 ADN COMPRESSION — detecta el patrón de "resorte comprimido":
    MA25/50/99 se agrupan mientras MA7 las cruza 2-3 veces (compresión real,
    no ruido) -> ignición (vela(s) anómalas vs el promedio de la compresión)
    -> régimen de pullbacks a MA7 sin tocar MA25 -> el toque de MA25 marca
    el fin del movimiento. Mismo patrón fractal en 5m (micro/scalp) y en 1D
    (macro/swing) — solo cambia la temporalidad de las velas que se leen.
    """

    def __init__(self):
        self.timeout = 5

    def analyze(self, req: AdnCompressionScanRequest) -> AdnCompressionScanResponse:
        logger.info(f"[ADN-COMPRESSION] Scanning {len(req.symbols)} symbols @ {req.timeframe}...")
        qualified: List[AdnCompressionItem] = []

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(self._analyze_symbol, s, req.timeframe): s for s in req.symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    item = future.result()
                    if item:
                        qualified.append(item)
                except Exception as e:
                    logger.warning(f"[ADN-COMPRESSION] Error analyzing {symbol}: {e}")

        qualified.sort(key=lambda it: (
            _PHASE_PRIORITY.get(it.phase, 0),
            it.ma7_crossings,
            it.ignition_multiplier,
        ), reverse=True)

        return AdnCompressionScanResponse(
            top_10=qualified[:10],
            scanned_count=len(req.symbols),
            qualified_count=len(qualified),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _analyze_symbol(self, symbol: str, timeframe: str) -> Optional[AdnCompressionItem]:
        klines = self._fetch_klines(symbol, interval=timeframe, limit=250)
        if not klines or len(klines) < 150:
            return None

        opens = [float(k[1]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]

        ma7 = _sma(closes, 7)
        ma25 = _sma(closes, 25)
        ma50 = _sma(closes, 50)
        ma99 = _sma(closes, 99)

        valid_from = 98  # primer índice donde las 4 medias ya tienen dato
        n = len(closes)
        if n - valid_from < MIN_COMPRESSION_CANDLES + 2:
            return None

        # ── Fase 1: buscar la ventana de compresión real más reciente ──────
        search_start = max(valid_from, n - SEARCH_LOOKBACK)
        compressed = []
        for i in range(search_start, n):
            pack = (ma25[i], ma50[i], ma99[i])
            spread_pct = (max(pack) - min(pack)) / closes[i] * 100.0
            compressed.append(spread_pct <= MAX_SPREAD_PCT)

        # Buscar el run contiguo de True más reciente que termine al menos
        # 1 vela antes del final (para dejar lugar a una posible ignición).
        run_end_rel = None
        run_start_rel = None
        i = len(compressed) - 2  # -2: dejamos al menos 1 vela después del run
        while i >= 0:
            if compressed[i]:
                end = i
                start = i
                while start - 1 >= 0 and compressed[start - 1]:
                    start -= 1
                if end - start + 1 >= MIN_COMPRESSION_CANDLES:
                    run_end_rel, run_start_rel = end, start
                    break
                i = start - 1
            else:
                i -= 1

        if run_end_rel is None:
            return None  # nunca hubo compresión real -> descartar (filtro anti-amague)

        run_end = search_start + run_end_rel
        run_start = search_start + run_start_rel

        # ── "ADN": cruces de MA7 contra el centro del paquete dentro del run ──
        mid = [(ma25[j] + ma50[j] + ma99[j]) / 3.0 for j in range(run_start, run_end + 1)]
        signs = [1 if ma7[j] > mid[k] else -1 for k, j in enumerate(range(run_start, run_end + 1))]
        crossings = sum(1 for k in range(1, len(signs)) if signs[k] != signs[k - 1])
        if crossings < MIN_ADN_CROSSINGS:
            return None  # el paquete estuvo cerca pero MA7 no lo "tejió" -> no es ADN real

        compression_candles = run_end - run_start + 1
        baseline_range = sum(highs[j] - lows[j] for j in range(run_start, run_end + 1)) / compression_candles
        if baseline_range <= 0:
            return None

        # ── Fase 2: ignición post-compresión ──────────────────────────────
        post_idx = list(range(run_end + 1, n))
        ignition_multiplier = 0.0
        ignition_start = None
        if post_idx:
            ratios = [(highs[j] - lows[j]) / baseline_range for j in post_idx]
            ignition_multiplier = max(ratios)
            if ignition_multiplier >= IGNITION_MULTIPLIER_THRESHOLD:
                ignition_start = post_idx[ratios.index(ignition_multiplier)]

        current_price = closes[-1]
        ma7_now, ma25_now, ma99_now = ma7[-1], ma25[-1], ma99[-1]
        dist_to_ma7_pct = abs(current_price - ma7_now) / current_price * 100.0
        dist_to_ma25_pct = abs(current_price - ma25_now) / current_price * 100.0

        reasons = [f"[ADN] Compresión real: {compression_candles} velas, {crossings} cruces de MA7"]

        if ignition_start is None:
            return AdnCompressionItem(
                symbol=symbol, timeframe=timeframe, phase="COILED", direction="NONE",
                ma7_crossings=crossings, compression_candles=compression_candles,
                ignition_multiplier=round(ignition_multiplier, 2), candles_since_ignition=0,
                current_price=current_price, ma7_now=ma7_now, ma25_now=ma25_now, ma99_now=ma99_now,
                dist_to_ma7_pct=round(dist_to_ma7_pct, 3), dist_to_ma25_pct=round(dist_to_ma25_pct, 3),
                touched_ma25_since_ignition=False,
                reasons=reasons + ["Compresión confirmada, esperando vela de ignición"],
            )

        direction = "LONG" if closes[-1] > closes[run_end] else "SHORT"
        candles_since_ignition = n - 1 - ignition_start

        if direction == "LONG":
            touched_ma25 = any(lows[j] <= ma25[j] for j in range(ignition_start, n))
        else:
            touched_ma25 = any(highs[j] >= ma25[j] for j in range(ignition_start, n))

        if touched_ma25:
            phase = "EXHAUSTED"
            reasons.append("Ignición confirmada, pero el precio ya tocó MA25 — movimiento agotado")
        elif dist_to_ma7_pct <= PULLBACK_TOLERANCE_PCT:
            phase = "PULLBACK_TO_MA7"
            reasons.append(f"Ignición x{ignition_multiplier:.1f} — precio respirando en MA7, reentrada válida")
        else:
            phase = "EXTENDED"
            reasons.append(f"Ignición x{ignition_multiplier:.1f} — precio extendido, esperar pullback a MA7")

        return AdnCompressionItem(
            symbol=symbol, timeframe=timeframe, phase=phase, direction=direction,
            ma7_crossings=crossings, compression_candles=compression_candles,
            ignition_multiplier=round(ignition_multiplier, 2), candles_since_ignition=candles_since_ignition,
            current_price=current_price, ma7_now=ma7_now, ma25_now=ma25_now, ma99_now=ma99_now,
            dist_to_ma7_pct=round(dist_to_ma7_pct, 3), dist_to_ma25_pct=round(dist_to_ma25_pct, 3),
            touched_ma25_since_ignition=touched_ma25,
            reasons=reasons,
        )

    def _fetch_klines(self, symbol: str, interval: str, limit: int) -> Optional[List[list]]:
        clean_symbol = symbol.replace('/', '').replace('-', '').upper()

        def _do_fetch():
            try:
                url = "https://fapi.binance.com/fapi/v1/klines"
                params = {'symbol': clean_symbol, 'interval': interval, 'limit': limit}
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"[ADN-COMPRESSION] Failed to fetch {symbol} from Binance Futures: {e}")
                try:
                    url = "https://api.binance.com/api/v3/klines"
                    params = {'symbol': clean_symbol, 'interval': interval, 'limit': limit}
                    response = requests.get(url, params=params, timeout=self.timeout)
                    response.raise_for_status()
                    return response.json()
                except Exception as e2:
                    logger.error(f"[ADN-COMPRESSION] Failed to fetch {symbol} from Binance Spot: {e2}")
                    return None

        return get_or_fetch(clean_symbol, interval, limit, _do_fetch)

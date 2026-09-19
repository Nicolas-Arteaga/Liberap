"""
DIAGNÓSTICO parte 2: ¿el motor DETECTA los trades reales de MA Slope Caso 3?

Para cada uno de los 45 trades reales (scratch_caso3_gt.json), en el bar de la
señal ±3 velas de 5m, corre el `_read_ma_geometry` + `_evaluate_ma_geometry_profile`
REALES del agente con la config de Caso 3 recuperada de los 9 scripts de julio
(SHORT-only, order ma7>ma25>ma50>ma99, slope prior≥0.2→current≤−0.2,
peakProximity recentHigh lb10 tol1.0). minRR NO afecta la geometría (solo el
sizing), así que este test es independiente del conflicto 3-vs-4.

Salida: cuántos trades reales el motor "ve" como candidato Caso 3 en su bar,
y por qué NO cuando no.
"""
import os, sys, json, bisect
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))
ROOT = os.path.join(HERE, "..", "..")

from engine import BacktestEngine, BASE_INTERVAL, BASE_MS  # noqa

CASO3_PROFILE = {
    "id": "diag-caso3", "name": "MA Slope Caso 3",
    "allowLong": False, "allowShort": True,
    "tpMultiplier": 3.0, "slMultiplier": 0.8, "minRR": 4.0,
    "marginPerTrade": 150.0, "maxOpenPositions": 3, "maxTradeDurationCandles": 192,
    "strategyType": "MaGeometry",
    "patternParamsJson": json.dumps({
        "timeframe": "1h",
        "order": {"ma7VsMa25": "greater", "ma7VsMa50": "greater", "ma7VsMa99": "greater"},
        "slope": {"targetMa": "ma7", "windowCandles": 3, "currentOp": "lte", "currentDeg": -0.2,
                  "priorOp": "gte", "priorDeg": 0.2},
        "touch": {"enabled": False}, "distanceBetweenMas": {"enabled": False},
        "contextSlope": {"enabled": False},
        "peakProximity": {"enabled": True, "type": "recentHigh", "lookbackCandles": 10, "tolerancePct": 1.0},
        "exit": {"slReference": "recentHigh", "slLookbackCandles": 10, "slBufferPct": 1.0, "tpMinPct": 10.0},
    }),
}
INTERVAL = "1h"


def main():
    J = json.load(open(os.path.join(ROOT, "scratch_caso3_gt.json")))
    eng = BacktestEngine()
    avail = set(eng.available_symbols())

    fires_at_signal = 0
    fires_nearby = 0
    no_fire = 0
    no_data = 0
    fires_ever_in_window = 0
    detail = []
    for j in J:
        sym = j["sym"]
        if sym not in avail:
            no_data += 1
            detail.append((sym, "NO_KLINES")); continue
        sig = int(datetime.fromisoformat(j["open_utc"]).timestamp() * 1000)
        eng.fetcher.set_active_symbol(sym, intervals=(BASE_INTERVAL, INTERVAL))
        rb, tb = eng.fetcher._active_by_interval[BASE_INTERVAL]

        hit = None
        # probar en ±6 velas de 5m alrededor de la señal
        i0 = bisect.bisect_left(tb, sig) - 6
        for k in range(max(1, i0), min(len(rb), bisect.bisect_left(tb, sig) + 7)):
            now = rb[k][0] + BASE_MS
            eng.fetcher.set_now(now)
            geo = eng.ma_agent._read_ma_geometry(sym, interval=INTERVAL)
            if not geo:
                continue
            cand = eng.ma_agent._evaluate_ma_geometry_profile(CASO3_PROFILE, geo)
            if cand:
                dt_min = (now - sig) / 60000
                if hit is None or abs(dt_min) < abs(hit[1]):
                    hit = (now, dt_min)
        # ¿dispara en algún momento de las 48h de vida del trade?
        ever = False
        cl = int(datetime.fromisoformat(j["close_utc"]).timestamp() * 1000)
        i1 = bisect.bisect_left(tb, sig); i2 = bisect.bisect_right(tb, cl)
        for k in range(max(1, i1 - 12), min(len(rb), i2)):
            now = rb[k][0] + BASE_MS
            eng.fetcher.set_now(now)
            geo = eng.ma_agent._read_ma_geometry(sym, interval=INTERVAL)
            if geo and eng.ma_agent._evaluate_ma_geometry_profile(CASO3_PROFILE, geo):
                ever = True; break
        if ever:
            fires_ever_in_window += 1

        if hit is None:
            no_fire += 1
            detail.append((sym, f"NO_FIRE ±30min (ever_in_48h={ever})"))
        elif abs(hit[1]) <= 65:   # dentro de 1 vela de 1h
            fires_at_signal += 1
            detail.append((sym, f"FIRE @ {hit[1]:+.0f}min"))
        else:
            fires_nearby += 1
            detail.append((sym, f"FIRE cerca @ {hit[1]:+.0f}min"))

    n = len(J)
    print("=" * 70)
    print(f"DETECCIÓN del motor sobre los {n} trades REALES de MA Slope Caso 3")
    print("=" * 70)
    print(f"  el motor dispara Caso 3 EN el bar de la señal (±1h): {fires_at_signal}/{n}")
    print(f"  dispara cerca (±30min-6velas):                        {fires_nearby}/{n}")
    print(f"  NO dispara en ±30min:                                 {no_fire}/{n}")
    print(f"  sin klines:                                           {no_data}/{n}")
    print(f"  (dispara en ALGÚN momento de las 48h de vida):        {fires_ever_in_window}/{n}")
    print()
    print("detalle:")
    for s, d in detail:
        print(f"  {s:14} {d}")


if __name__ == "__main__":
    main()

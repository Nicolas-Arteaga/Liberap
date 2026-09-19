"""
PHASE 2 - A/B: reconstruccion del timeline real de produccion + medicion del
desfasaje de deteccion del replay.

Para los 113 trades reales de MA Slope Caso 2:
  * signal ts        = AgentDecisionJson.captured_at_utc
  * market snap ts    = position_sizing.market_context.captured_at_utc
  * entry ts          = SimulatedTrades.OpenedAt
  * latencias
  * ocupacion REAL de cupos de MA Slope Caso 2 en el instante de entrada
  * ocupacion CRUZADA (otra estrategia con posicion abierta en ese simbolo)
  * cycle_candidates_rejected (competidores reales por el cupo)
  * DESFASAJE: primera vela de 5m en que el candidate_fn del replay dispara
    ese simbolo, dentro de [-24h, +3h] alrededor de la señal real.

Lo que NO existe (se marca, no se inventa):
  * timestamp de "el scanner llego al simbolo X" separado de captured_at_utc
  * log de uptime del agente minuto a minuto
  * ranking exacto post-bucket_calibrator (multiplicador historico no reconstruible)

Salida: scratch_phase2_timeline.csv + stdout con distribuciones.
"""
import os, sys, csv, json, bisect, subprocess, statistics as st
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))
ROOT = os.path.join(HERE, "..", "..")

from engine import BacktestEngine, BASE_INTERVAL, BASE_MS, ARG_OFFSET_MS  # noqa

REAL_CSV = os.path.join(ROOT, "scratch_ma2_real.csv")
ALL_CSV = os.path.join(ROOT, "scratch_all_trades_p2.csv")
OUT = os.path.join(ROOT, "scratch_phase2_timeline.csv")


def pms(s):
    if not s:
        return None
    s = s.strip().replace("T", " ").replace("Z", "")
    for x in ("+00:00", "+00"):
        if s.endswith(x):
            s = s[:-len(x)].strip()
    if "." in s:
        h, fr = s.split("."); s = h + "." + (fr + "000000")[:6]
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
    else:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def load_profile():
    q = ('SELECT row_to_json(t) FROM (SELECT "Id" as id,"Name" as name,"AllowLong" as "allowLong",'
         '"AllowShort" as "allowShort","TpMultiplier" as "tpMultiplier","SlMultiplier" as "slMultiplier",'
         '"MinRR" as "minRR","MarginPerTrade" as "marginPerTrade","MaxOpenPositions" as "maxOpenPositions",'
         '"MaxTradeDurationCandles" as "maxTradeDurationCandles","PatternParamsJson" as "patternParamsJson" '
         "FROM \"StrategyProfiles\" WHERE \"Name\"='MA Slope Caso 2') t;")
    return json.loads(subprocess.check_output(
        ["docker", "exec", "verge-db", "psql", "-U", "postgres", "-d", "Verge", "-t", "-A", "-c", q]).decode().strip())


def main():
    prof = load_profile()
    interval = json.loads(prof["patternParamsJson"]).get("timeframe", "1h")
    reals = list(csv.DictReader(open(REAL_CSV, encoding="utf-8", errors="replace")))

    # ── ocupacion cruzada: intervalos [open, close) por simbolo, TODAS las estrategias ──
    occ = {}
    ma2_intervals = []
    for r in csv.DictReader(open(ALL_CSV, encoding="utf-8", errors="replace")):
        o, c = pms(r["OpenedAt"]), pms(r["ClosedAt"])
        if o and c:
            occ.setdefault(r["Symbol"], []).append((o, c, r["Name"]))
            if r["Name"] == "MA Slope Caso 2":
                ma2_intervals.append((o, c))
    for s in occ:
        occ[s].sort()
    ma2_intervals.sort()

    def ma2_slots_at(ts, exclude_open):
        return sum(1 for (o, c) in ma2_intervals if o <= ts < c and o != exclude_open)

    def cross_occupied_at(sym, ts, own_open):
        for (o, c, name) in occ.get(sym, []):
            if o == own_open and name == "MA Slope Caso 2":
                continue
            if o <= ts < c:
                return name
        return None

    eng = BacktestEngine()
    avail = set(eng.available_symbols())

    rows_out = []
    lat_dec, lat_mkt = [], []
    dfirst = []          # (replay first fire) - (real signal), en minutos
    persistence = []     # cuantas velas de 5m dispara el replay en [-24h,+3h]
    cross_block_at_real = 0
    cross_block_at_first = 0
    replayable = 0
    for r in reals:
        sym = r["Symbol"]
        try:
            d = json.loads(r["AgentDecisionJson"]) if r["AgentDecisionJson"] else {}
        except Exception:
            d = {}
        sig = pms(d.get("captured_at_utc"))
        mkt = pms((d.get("position_sizing") or {}).get("market_context", {}).get("captured_at_utc"))
        ent = pms(r["OpenedAt"])
        if sig and ent:
            lat_dec.append((ent - sig) / 1000)
        if mkt and ent:
            lat_mkt.append((ent - mkt) / 1000)
        ccr = d.get("cycle_candidates_rejected", []) or []
        real_competitors = [c for c in ccr if "src_not_allowed" not in str(c.get("reason", ""))]
        slots_now = ma2_slots_at(ent, ent)
        cross_now = cross_occupied_at(sym, sig or ent, ent)

        first_fire = None
        npers = 0
        if sym in avail and sig:
            eng.fetcher.set_active_symbol(sym, intervals=(BASE_INTERVAL, interval))
            base_rows, base_t = eng.fetcher._active_by_interval[BASE_INTERVAL]
            t0 = sig - 24 * 3600 * 1000
            t1 = sig + 3 * 3600 * 1000
            i0 = bisect.bisect_left(base_t, t0)
            i1 = bisect.bisect_right(base_t, t1)
            for k in range(i0, i1):
                now = base_rows[k][0] + BASE_MS
                eng.fetcher.set_now(now)
                geo = eng.ma_agent._read_ma_geometry(sym, interval=interval)
                if not geo:
                    continue
                cand = eng.ma_agent._evaluate_ma_geometry_profile(prof, geo)
                if cand:
                    npers += 1
                    if first_fire is None:
                        first_fire = now
            if first_fire is not None:
                replayable += 1
                dfirst.append((first_fire - sig) / 60000)
                persistence.append(npers)
                if cross_occupied_at(sym, first_fire, ent):
                    cross_block_at_first += 1
                if cross_now:
                    cross_block_at_real += 1

        rows_out.append({
            "symbol": sym,
            "signal_ts": datetime.utcfromtimestamp(sig/1000).isoformat() if sig else "",
            "mkt_snap_ts": datetime.utcfromtimestamp(mkt/1000).isoformat() if mkt else "",
            "entry_ts": datetime.utcfromtimestamp(ent/1000).isoformat() if ent else "",
            "lat_dec_s": round((ent - sig) / 1000, 1) if (sig and ent) else "",
            "lat_mkt_s": round((ent - mkt) / 1000, 1) if (mkt and ent) else "",
            "ma2_slots_occupied_at_entry": slots_now,
            "cross_strategy_holding_symbol_at_signal": cross_now or "",
            "n_real_competitors_same_slot": len(real_competitors),
            "replay_first_fire_ts": datetime.utcfromtimestamp(first_fire/1000).isoformat() if first_fire else "NO_FIRE_OR_UNREPLAYABLE",
            "replay_first_fire_delta_min": round((first_fire - sig) / 60000, 1) if (first_fire and sig) else "",
            "replay_pattern_persistence_bars_5m": npers,
        })

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)

    def summ(x, n):
        if not x:
            print(f"{n}: (vacio)"); return
        x = sorted(x)
        print(f"{n}: n={len(x)} min={x[0]:.1f} p10={x[len(x)//10]:.1f} p25={x[len(x)//4]:.1f} "
              f"median={st.median(x):.1f} p75={x[3*len(x)//4]:.1f} p90={x[9*len(x)//10]:.1f} max={x[-1]:.1f}")

    print("=" * 78)
    print("PHASE 2 — TIMELINE RECONSTRUCTION (113 trades reales, MA Slope Caso 2)")
    print("=" * 78)
    print(f"\ntabla completa -> {OUT}")
    print("\n## LATENCIAS (dato REAL disponible)")
    summ(lat_dec, "  decision (captured_at_utc) -> entry (OpenedAt)   [seg]")
    summ(lat_mkt, "  market snapshot -> entry (OpenedAt)              [seg]")
    print("\n## DATO QUE NO EXISTE (marcado, no inventado)")
    print("  - timestamp separado de 'el scanner llego al simbolo X' (captured_at_utc ya es el punto de decision)")
    print("  - log de uptime del agente minuto a minuto")
    print("  - multiplicador historico de bucket_calibrator (ranking exacto post-orden)")
    print("\n## OCUPACION DE CUPOS DE MA SLOPE CASO 2 EN EL INSTANTE DE ENTRADA (reconstruido de trades reales)")
    from collections import Counter
    print("  ", Counter(r["ma2_slots_occupied_at_entry"] for r in rows_out))
    print("\n## COMPETIDORES REALES por el mismo cupo (cycle_candidates_rejected, no src_not_allowed)")
    summ([r["n_real_competitors_same_slot"] for r in rows_out], "  competidores")
    print("\n## OCUPACION CRUZADA — otra estrategia tenia posicion abierta en ese simbolo")
    print(f"  en el instante de la SEÑAL real: {sum(1 for r in rows_out if r['cross_strategy_holding_symbol_at_signal'])}/{len(rows_out)}")
    print(f"  (esperado ~0: produccion abrio, asi que _should_skip no bloqueaba en ese momento)")
    print("\n## DESFASAJE DE DETECCION DEL REPLAY (primera vela que dispara - señal real) [minutos]")
    summ(dfirst, "  delta_first")
    neg = sum(1 for x in dfirst if x <= -30)
    print(f"  replay dispara >=30 min ANTES que la señal real: {neg}/{len(dfirst)}")
    print(f"  replay dispara en +-30 min de la señal real:      {sum(1 for x in dfirst if -30 < x < 30)}/{len(dfirst)}")
    print("\n## PERSISTENCIA DEL PATRON (velas de 5m que el replay dispara en [-24h,+3h])")
    summ(persistence, "  bars")
    print("\n## ¿La mascara de ocupacion CRUZADA empujaria el primer disparo del replay hacia la hora real?")
    print(f"  simbolo ocupado por otra estrategia en el 1er disparo del replay: {cross_block_at_first}/{replayable}")
    print(f"  simbolo ocupado por otra estrategia en la señal real:            {cross_block_at_real}/{replayable}")


if __name__ == "__main__":
    main()

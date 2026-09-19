"""
FASE SIGUIENTE — separar (1) alpha de Caso 3  (2) politica de admision de slots
(3) timeout  (4) minRR 3 vs 4.  TODO causal: ninguna decision de entrada usa el
resultado futuro de la operacion. Sin optimizacion, sin grid, sin ML, sin
thresholds nuevos.

Sizing respetado: $450/estrategia, $150/trade, max 3 simultaneas. Caso 3 compite
por SUS 3 cupos (cap por-estrategia). La competencia entre-estrategias se modela
aparte con la mascara `occupied` (opt-in, flag --occupied).

Paso 1 (caro, 1 vez, cacheado): ma_precompute() con la config de Caso 3 de julio
(SHORT-only) sobre TODO el universo con klines, en la ventana real de Caso 3.
De ahi se extrae un stream compacto de candidatos {bucket, symbol, risk, score}.

Paso 2 (barato, se itera): loop de reloj global de 5m con cap estricto de 3
cupos. Politicas de admision (todas SIN info futura):
  fifo      -> orden de escaneo de produccion (orden del watchlist = pc['active'])
  oldest    -> el candidato cuyo patron se hizo elegible antes (FIFO real)
  sym_asc   -> alfabetico  (lo que uso el baseline de Gate V4)
  sym_desc  -> alfabetico inverso
  shuffle   -> 20 seeds (desempate aleatorio) -> distribucion
  realpool  -> [DIAGNOSTICO, usa hindsight] elegibles restringidos a los simbolos
               que Caso 3 realmente opero -> cota superior de "si supieramos que
               simbolos elegir"
minRR: se aplica como filtro sobre el `risk` ya calculado (rr = |tp-e|/|sl-e|),
en 3 vistas {0.5 ~= produccion, 3.0, 4.0} sin re-precomputar.
timeout: cierre incondicional a T horas (48 = fiel a produccion segun el cluster
de cierres reales en 48.0-48.3h; 192 = maxTradeDurationCandles*1h; 720 = tope duro).
"""
import os, sys, json, pickle, sqlite3, bisect, statistics, collections
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))
ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CACHE = os.path.join(HERE, "scratch_slot_candstream.pkl")

from engine import BacktestEngine, BASE_MS  # noqa

WIN_A = int(datetime(2026, 7, 10, tzinfo=timezone.utc).timestamp() * 1000)
WIN_B = int(datetime(2026, 8, 14, tzinfo=timezone.utc).timestamp() * 1000)
KL_END = int(datetime(2026, 8, 23, tzinfo=timezone.utc).timestamp() * 1000)
FEE = 0.0004
MARGIN = 150.0

CASO3_PROFILE = {
    "id": "phase-caso3", "name": "MA Slope Caso 3",
    "allowLong": False, "allowShort": True,
    "tpMultiplier": 3.0, "slMultiplier": 0.8, "minRR": 0.5,   # faithful: sin veto RR efectivo
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


def build_candstream():
    if os.path.exists(CACHE):
        print("cache hit:", CACHE)
        return pickle.load(open(CACHE, "rb"))
    eng = BacktestEngine()
    syms = eng.available_symbols()
    print(f"precompute: {len(syms)} simbolos, ventana {datetime.utcfromtimestamp(WIN_A/1000)} -> {datetime.utcfromtimestamp(WIN_B/1000)}")
    done = [0]

    def cb(i, n):
        if i - done[0] >= 40 or i == n:
            print(f"  {i}/{n}"); done[0] = i

    pc = eng.ma_precompute(CASO3_PROFILE, syms, WIN_A, WIN_B, fidelity=None, progress_cb=cb)
    # stream compacto: por symbol, lista ordenada de (bucket, risk, score); + primer bucket elegible
    stream = []
    first_elig = {}
    for sym, fr in pc["ready"].items():
        for b, e in sorted(fr.items()):
            r = e["risk"]
            stream.append((int(b), sym, float(r["entry_price"]), float(r["sl_price"]),
                           float(r["tp_price"]), int(r["side"]), float(e.get("score", 0) or 0)))
            first_elig.setdefault(sym, int(b))
    stream.sort()
    out = {"stream": stream, "first_elig": first_elig, "active_order": list(pc["active"]),
           "interval_ms": pc["interval_ms"], "slots": pc["slots"], "n_syms": len(syms)}
    pickle.dump(out, open(CACHE, "wb"))
    print(f"stream: {len(stream)} fires de patron, {len(pc['ready'])} simbolos con >=1 fire")
    return out


# ---- klines cache para el exit-sim ----
_KL = {}
def kl5(conn, sym):
    if sym not in _KL:
        _KL[sym] = conn.execute(
            "SELECT open_time,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' "
            "AND open_time>=? AND open_time<=? ORDER BY open_time", (sym, WIN_A - 3 * 3600000, KL_END)).fetchall()
    return _KL[sym]


def sim_exit(conn, sym, side, entry, sl, tp, open_ms, timeout_h):
    """side 1 = SHORT. cierre incondicional a timeout_h. Devuelve (reason, exit_px, close_ms)."""
    kl = kl5(conn, sym)
    i = bisect.bisect_right([k[0] for k in kl], open_ms)
    cap = open_ms + timeout_h * 3600000
    for ot, h, l, c in kl[i:]:
        if side == 1:
            if l <= tp:
                return "TP", tp, ot + BASE_MS
            if h >= sl:
                return "SL", sl, ot + BASE_MS
        else:
            if h >= tp:
                return "TP", tp, ot + BASE_MS
            if l <= sl:
                return "SL", sl, ot + BASE_MS
        if ot + BASE_MS >= cap:
            return "TIMEOUT", c, ot + BASE_MS
    return "NODATA", kl[-1][3] if kl else entry, (kl[-1][0] if kl else open_ms) + BASE_MS


def pnl_of(side, entry, exit_px):
    qty = MARGIN / entry
    gross = qty * (entry - exit_px) if side == 1 else qty * (exit_px - entry)
    return gross - (qty * entry + qty * exit_px) * FEE


def metrics(trades, label):
    if not trades:
        return dict(policy=label, n=0, net=0.0, pf=0.0, wr=0, dd=0.0,
                    tp=0, sl=0, to=0, nd=0)
    pn = [t["pnl"] for t in trades]
    pos = sum(p for p in pn if p > 0); neg = -sum(p for p in pn if p < 0)
    eq = 450.0; peak = eq; dd = 0.0
    for t in sorted(trades, key=lambda x: x["close_ms"]):
        eq += t["pnl"]; peak = max(peak, eq); dd = min(dd, eq - peak)
    ex = collections.Counter(t["reason"] for t in trades)
    return dict(policy=label, n=len(trades), net=round(sum(pn), 1),
                pf=round(pos / neg, 2) if neg else 99.0,
                wr=round(100 * sum(1 for p in pn if p > 0) / len(pn)),
                dd=round(dd, 1), tp=ex.get("TP", 0), sl=ex.get("SL", 0),
                to=ex.get("TIMEOUT", 0), nd=ex.get("NODATA", 0))


_OCC = None
def occ_mask():
    global _OCC
    if _OCC is None:
        p = os.path.join(ROOT, "scratch_occ_mask.json")
        _OCC = {k: [tuple(x) for x in v] for k, v in json.load(open(p)).items()} if os.path.exists(p) else {}
    return _OCC

def _is_occ(sym, ts):
    for o, c in occ_mask().get(sym, ()):
        if o <= ts < c:
            return True
        if o > ts:
            break
    return False


def run_policy(conn, cs, policy, min_rr, timeout_h, seed=0, real_syms=None, use_occ=False):
    stream, first_elig = cs["stream"], cs["first_elig"]
    scan_rank = {s: i for i, s in enumerate(cs["active_order"])}
    slots, iv = cs["slots"], cs["interval_ms"]
    import random
    rng = random.Random(seed)
    # index stream por bucket
    by_bucket = collections.defaultdict(list)
    for b, sym, e, sl, tp, side, sc in stream:
        rr = abs(tp - e) / abs(sl - e) if abs(sl - e) > 1e-12 else 0
        if rr < min_rr:
            continue
        if real_syms is not None and sym not in real_syms:
            continue
        by_bucket[b].append((sym, e, sl, tp, side, sc, rr))

    t0 = WIN_A - (WIN_A % BASE_MS)
    open_tr = {}
    last_day = {}
    done = []
    displaced = set()
    occ_samples = []
    now = t0
    while now <= KL_END:
        # cerrar
        for sym in list(open_tr):
            ot = open_tr[sym]
            if ot["close_ms"] <= now:
                done.append(ot); del open_tr[sym]
        occ_samples.append(len(open_tr))
        free = slots - len(open_tr)
        bucket = now - (now % iv)
        # CAUSAL: solo fires de buckets 1h YA CERRADOS (el bar de la senal cerro
        # en <= bucket). Ventana de persistencia = ultimas 3 horas cerradas, para
        # no perder la senal si los 3 cupos estuvieron llenos toda una hora.
        cmap = {}
        for kk in (bucket - iv, bucket - 2 * iv, bucket - 3 * iv):
            for c in by_bucket.get(kk, ()):
                cmap.setdefault(c[0], c)   # el mas reciente (kk mayor primero)
        cands = list(cmap.values())
        if cands:
            day = datetime.utcfromtimestamp(now / 1000).date()
            elig = [c for c in cands if c[0] not in open_tr and last_day.get(c[0]) != day
                    and not (use_occ and _is_occ(c[0], now))]
            if policy == "fifo":
                elig.sort(key=lambda c: scan_rank.get(c[0], 1 << 30))
            elif policy == "oldest":
                elig.sort(key=lambda c: first_elig.get(c[0], 1 << 62))
            elif policy == "sym_asc":
                elig.sort(key=lambda c: c[0])
            elif policy == "sym_desc":
                elig.sort(key=lambda c: c[0], reverse=True)
            elif policy == "shuffle":
                rng.shuffle(elig)
            elif policy == "realpool":
                elig.sort(key=lambda c: c[0])
            if free > 0:
                for sym, e, sl, tp, side, sc, rr in elig[:free]:
                    rsn, xpx, cms = sim_exit(conn, sym, side, e, sl, tp, now, timeout_h)
                    open_tr[sym] = dict(symbol=sym, side=side, open_ms=now, entry=e, sl=sl, tp=tp,
                                        reason=rsn, exit_px=xpx, close_ms=cms, pnl=pnl_of(side, e, xpx),
                                        day=day.isoformat())
                    last_day[sym] = day
                for sym, *_ in elig[free:]:
                    displaced.add((sym, bucket))
            else:
                for sym, *_ in elig:
                    displaced.add((sym, bucket))
        now += BASE_MS
    for sym in list(open_tr):
        done.append(open_tr[sym])
    m = metrics(done, policy)
    m["displaced"] = len(displaced)
    m["slot_util"] = round(statistics.mean(occ_samples) / slots, 3)
    m["max_conc"] = max(occ_samples) if occ_samples else 0
    return m, done


def real_lifecycle(conn, timeout_h):
    """Politica A: las 45 senales reales, mismo exit-sim (timeout incondicional)."""
    J = json.load(open(os.path.join(ROOT, "scratch_caso3_gt.json")))
    tr = []
    for j in J:
        op = int(datetime.fromisoformat(j["open_utc"]).timestamp() * 1000)
        e, sl, tp = j["entry"], j["sl"], j["tp"]
        rsn, xpx, cms = sim_exit(conn, j["sym"], 1, e, sl, tp, op, timeout_h)
        tr.append(dict(symbol=j["sym"], side=1, open_ms=op, entry=e, sl=sl, tp=tp,
                       reason=rsn, exit_px=xpx, close_ms=cms, pnl=pnl_of(1, e, xpx),
                       day=datetime.utcfromtimestamp(op / 1000).date().isoformat()))
    return tr


def real_asrun():
    """Politica A base: PnL real tal cual (trades.csv)."""
    J = json.load(open(os.path.join(ROOT, "scratch_caso3_gt.json")))
    pn = [j["pnl"] for j in J]
    pos = sum(p for p in pn if p > 0); neg = -sum(p for p in pn if p < 0)
    return dict(policy="REAL as-run (trades.csv $)", n=len(J), net=round(sum(pn), 1),
                pf=round(pos / neg, 2), wr=round(100 * sum(1 for p in pn if p > 0) / len(pn)),
                dd="-", tp=sum(1 for j in J if j["real_outcome"] == "TP"),
                sl=sum(1 for j in J if j["real_outcome"] == "SL"),
                to=sum(1 for j in J if j["real_outcome"] == "TIMEOUT"), displaced=0)


def main():
    cs = build_candstream()
    conn = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    J = json.load(open(os.path.join(ROOT, "scratch_caso3_gt.json")))
    real_sd = {(j["sym"], datetime.fromisoformat(j["open_utc"]).date().isoformat()) for j in J}
    real_syms = {j["sym"] for j in J}

    print("\n" + "=" * 100)
    print(f"STREAM DE CANDIDATOS: {len(cs['stream'])} fires de patron Caso 3, "
          f"{len(cs['first_elig'])} simbolos, universo {cs['n_syms']}")
    n_low = sum(1 for b, s, e, sl, tp, sd, sc in cs["stream"] if abs(tp - e) / abs(sl - e) < 3)
    n_lo4 = sum(1 for b, s, e, sl, tp, sd, sc in cs["stream"] if abs(tp - e) / abs(sl - e) < 4)
    print(f"  fires con RR<3: {n_low}/{len(cs['stream'])}   RR<4: {n_lo4}/{len(cs['stream'])}")

    rows = []
    rows.append(("REAL as-run", real_asrun()))
    for th in (48, 192, 720):
        rows.append((f"REAL signals + lifecycle (timeout {th}h)", metrics(real_lifecycle(conn, th), f"REAL-lc-{th}h")))

    print("\n" + "=" * 100)
    print("PRUEBA CLAVE — politicas de admision causales (minRR 0.5 ~=produccion, timeout 48h)")
    print("=" * 100)
    print(f"{'politica':<26}{'n':>4}{'net':>9}{'PF':>7}{'WR':>5}{'DD':>9}{'TP/SL/TO':>12}{'displ':>7}{'util':>7}{'ovlp(s,d)':>11}")
    for pol in ("fifo", "oldest", "sym_asc", "sym_desc", "realpool"):
        m, tr = run_policy(conn, cs, pol, 0.5, 48)
        ov = len({(t["symbol"], t["day"]) for t in tr} & real_sd)
        ovs = len({t["symbol"] for t in tr} & real_syms)
        exq = f"{m['tp']}/{m['sl']}/{m['to']}"
        ovq = f"{ov}/{ovs}"
        print(f"{pol:<26}{m['n']:>4}{m['net']:>9}{m['pf']:>7}{m['wr']:>4}%{m['dd']:>9}"
              f"{exq:>12}{m['displaced']:>7}{m['slot_util']:>7}{ovq:>11}")
    for pol in ("oldest", "shuffle"):
        accs = []
        for s in (range(20) if pol == "shuffle" else [0]):
            m, tr = run_policy(conn, cs, pol, 0.5, 48, seed=s, use_occ=True)
            accs.append(m)
        m0 = accs[len(accs) // 2] if len(accs) > 1 else accs[0]
        exq = f"{m0['tp']}/{m0['sl']}/{m0['to']}"
        tag = pol + " +occ(x-strat)" + (" P50" if len(accs) > 1 else "")
        posn = sum(1 for m in accs if m["net"] > 0)
        print(f"{tag:<26}{m0['n']:>4}{m0['net']:>9}{m0['pf']:>7}{m0['wr']:>4}%{m0['dd']:>9}"
              f"{exq:>12}{m0['displaced']:>7}{m0['slot_util']:>7}   {posn}/{len(accs)} net+")
    # shuffle distribution
    sh = [run_policy(conn, cs, "shuffle", 0.5, 48, seed=s)[0] for s in range(20)]
    pfs = sorted(m["pf"] for m in sh); nets = sorted(m["net"] for m in sh); wrs = sorted(m["wr"] for m in sh)
    print(f"{'shuffle x20 (P5/50/95)':<26}{sh[0]['n']:>4}"
          f"{f'{nets[1]:.0f}/{nets[10]:.0f}/{nets[18]:.0f}':>9}"
          f"{f'{pfs[1]:.2f}/{pfs[10]:.2f}/{pfs[18]:.2f}':>7}"
          f"  net-pos seeds: {sum(1 for m in sh if m['net']>0)}/20")

    print("\n" + "=" * 100)
    print("4. MINRR 3 vs 4 (sensibilidad; NO se elige el mejor). politica fifo, timeout 48h")
    print("=" * 100)
    print(f"{'minRR':<10}{'univ.fires':>12}{'n_exec':>9}{'net':>9}{'PF':>7}{'WR':>5}{'displ':>7}{'slot_util':>11}")
    for mr in (0.5, 3.0, 4.0):
        m, tr = run_policy(conn, cs, "fifo", mr, 48)
        univ = sum(1 for b, s, e, sl, tp, sd, sc in cs["stream"] if abs(tp - e) / abs(sl - e) >= mr)
        print(f"{mr:<10}{univ:>12}{m['n']:>9}{m['net']:>9}{m['pf']:>7}{m['wr']:>4}%{m['displaced']:>7}{m['slot_util']:>11}")

    print("\n" + "=" * 100)
    print("5. TIMEOUT — aislado (politica REAL signals + lifecycle; nada mas cambia)")
    print("=" * 100)
    for th in (48, 192, 720):
        m = metrics(real_lifecycle(conn, th), f"lc-{th}h")
        print(f"  timeout {th:>3}h: n={m['n']} net={m['net']:>7} PF={m['pf']:>5} WR={m['wr']}%  TP/SL/TO={m['tp']}/{m['sl']}/{m['to']}")

    print("\n" + "=" * 100)
    print("6. TABLA RESUMEN")
    print("=" * 100)
    print(f"{'variante':<42}{'n':>4}{'net':>9}{'PF':>7}{'WR':>5}{'TP/SL/TO':>12}")
    for lbl, m in rows:
        exq = f"{m.get('tp','-')}/{m.get('sl','-')}/{m.get('to','-')}"
        wrq = str(m.get('wr', '-')) + '%'
        print(f"{lbl:<42}{m.get('n',0):>4}{m.get('net','-'):>9}{m.get('pf','-'):>7}{wrq:>5}{exq:>12}")
    for pol in ("fifo", "oldest", "sym_asc"):
        m, tr = run_policy(conn, cs, pol, 0.5, 48)
        exq = f"{m['tp']}/{m['sl']}/{m['to']}"
        wrq = str(m['wr']) + '%'
        print(f"{'Caso3 causal slot: ' + pol:<42}{m['n']:>4}{m['net']:>9}{m['pf']:>7}{wrq:>5}{exq:>12}")
    m, tr = run_policy(conn, cs, "realpool", 0.5, 48)
    exq = f"{m['tp']}/{m['sl']}/{m['to']}"
    wrq = str(m['wr']) + '%'
    print(f"{'Caso3 realpool [hindsight, cota superior]':<42}{m['n']:>4}{m['net']:>9}{m['pf']:>7}{wrq:>5}{exq:>12}")

    json.dump({"stream_n": len(cs["stream"]), "n_syms": cs["n_syms"]},
              open(os.path.join(ROOT, "scratch_slot_causal_summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

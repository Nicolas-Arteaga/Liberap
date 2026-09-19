"""
GOLDEN REPLAY de MA Slope Caso 3 — test de si el backtester representa el
SISTEMA ACTUAL (no una version historica).

REGLA GLOBAL: NO ARTIFICIAL TIMEOUT. Una operacion permanece abierta hasta TP o
SL (o liquidacion, imposible a 1x). Si no toca ninguno antes del fin del dataset:
queda OPEN / CENSORED y se reporta aparte. NUNCA se convierte en perdida por
agotarse el dataset.

Lifecycle = reglas ACTUALES de produccion, auditadas del codigo:
  entry  = precio de la vela de senal (prod: precio vivo al escanear)
  SL     = max(highs[-10:]) * 1.01   (recentHigh + slBufferPct 1.0%, SHORT)
  TP     = entry - max(2.5*SL_dist, 10%*entry)
           (rr_target = min(tpMultiplier 3.0, TP_MULT_TREND_FOLLOWING_MAX 2.5)
            porque confluence_score=80 -> setup "Trend Following";
            luego piso min_tp_pct 10%)  --> ya viene calculado en risk[] del
            precompute por _calculate_position_nexus_style REAL
  exits  = SOLO tp_hit / sl_hit   (worker .NET 1s: TP/SL/liquidacion, sin timeout)
  fees   = 0.04% taker entry + exit sobre nocional
  funding= 0.01% del nocional cada 8h que la posicion este abierta (siempre adverso)
  sizing = $150 margen fijo, 1x, qty=150/entry. Max 3 simultaneas/estrategia ($450).
  slots  = al liberarse un cupo, entra el candidato de mayor score; para Caso 3
           el score es constante (80) -> desempate = orden de escaneo (~arbitrario).
           3/3 lleno -> el candidato se descarta ese ciclo (no hay cola).

Contrafactuales (senales reales SOLO como diagnostico):
  A  REAL historico (trades.csv, tal cual se ejecuto — bajo reglas viejas)
  B  replay lifecycle ACTUAL sobre las senales reales (sin competencia de slots)
  C  replay lifecycle ACTUAL + competencia causal por 3 cupos (pool completo)

Sin timeouts. Sin optimizar. Sin tocar parametros.
"""
import os, sys, json, pickle, sqlite3, bisect, statistics, collections
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CACHE = os.path.join(HERE, "scratch_slot_candstream.pkl")

BASE_MS = 5 * 60 * 1000
FEE = 0.0004
FUND_8H = 0.0001
MARGIN = 150.0
WIN_A = int(datetime(2026, 7, 10, tzinfo=timezone.utc).timestamp() * 1000)
KL_END = int(datetime(2026, 8, 23, tzinfo=timezone.utc).timestamp() * 1000)  # fin del dataset 5m util

_KL = {}
def kl5(conn, sym):
    if sym not in _KL:
        _KL[sym] = conn.execute(
            "SELECT open_time,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' "
            "AND open_time>=? AND open_time<=? ORDER BY open_time", (sym, WIN_A - 3 * 3600000, KL_END + 3600000)).fetchall()
    return _KL[sym]


def data_end(conn, sym):
    kl = kl5(conn, sym)
    return kl[-1][0] + BASE_MS if kl else KL_END


def sim_bracket(conn, sym, side, entry, sl, tp, open_ms):
    """SIN timeout. Devuelve (reason, exit_px, close_ms, censored_bool, last_px, obs_dur_h)."""
    kl = kl5(conn, sym)
    i = bisect.bisect_right([k[0] for k in kl], open_ms)
    for ot, h, l, c in kl[i:]:
        if side == 1:  # SHORT
            if l <= tp:
                return "tp_hit", tp, ot + BASE_MS, False, c, (ot + BASE_MS - open_ms) / 3600000
            if h >= sl:
                return "sl_hit", sl, ot + BASE_MS, False, c, (ot + BASE_MS - open_ms) / 3600000
        else:
            if h >= tp:
                return "tp_hit", tp, ot + BASE_MS, False, c, (ot + BASE_MS - open_ms) / 3600000
            if l <= sl:
                return "sl_hit", sl, ot + BASE_MS, False, c, (ot + BASE_MS - open_ms) / 3600000
    last = kl[-1] if kl else None
    de = (last[0] + BASE_MS) if last else KL_END
    return "OPEN_CENSORED", None, de, True, (last[3] if last else entry), (de - open_ms) / 3600000


def funding_cost(qty, ref_px, dur_h):
    n_events = int(dur_h // 8)
    return qty * ref_px * FUND_8H * n_events


def pnl_closed(side, entry, exit_px, dur_h):
    qty = MARGIN / entry
    gross = qty * (entry - exit_px) if side == 1 else qty * (exit_px - entry)
    fees = (qty * entry + qty * exit_px) * FEE
    fund = funding_cost(qty, (entry + exit_px) / 2, dur_h)
    return gross - fees - fund


def pnl_mtm(side, entry, last_px, dur_h):
    qty = MARGIN / entry
    gross = qty * (entry - last_px) if side == 1 else qty * (last_px - entry)
    fees = qty * entry * FEE  # solo entry (no cerro)
    fund = funding_cost(qty, (entry + last_px) / 2, dur_h)
    return gross - fees - fund


def agg(closed, censored, label):
    if not closed:
        return dict(policy=label, n=0, ncens=len(censored))
    pn = [t["pnl"] for t in closed]
    pos = sum(p for p in pn if p > 0); neg = -sum(p for p in pn if p < 0)
    eq = 450.0; peak = eq; dd = 0.0
    for t in sorted(closed, key=lambda x: x["close_ms"]):
        eq += t["pnl"]; peak = max(peak, eq); dd = min(dd, eq - peak)
    ex = collections.Counter(t["reason"] for t in closed)
    dur = [t["dur_h"] for t in closed]
    cens_dur = [t["dur_h"] for t in censored]
    cens_mtm = [t["mtm"] for t in censored]
    return dict(policy=label, n=len(closed), net=round(sum(pn), 1),
                pf=round(pos / neg, 2) if neg else 99.0,
                wr=round(100 * sum(1 for p in pn if p > 0) / len(pn)),
                dd=round(dd, 1), tp=ex.get("tp_hit", 0), sl=ex.get("sl_hit", 0),
                dur_med=round(statistics.median(dur), 1), dur_max=round(max(dur), 1),
                ncens=len(censored),
                cens_dur_med=round(statistics.median(cens_dur), 1) if cens_dur else 0,
                cens_dur_max=round(max(cens_dur), 1) if cens_dur else 0,
                cens_mtm_sum=round(sum(cens_mtm), 1) if cens_mtm else 0)


def policy_B(conn):
    """senales reales -> lifecycle actual, SIN competencia de slots, SIN timeout."""
    J = json.load(open(os.path.join(ROOT, "scratch_caso3_gt.json")))
    closed, cens = [], []
    for j in J:
        op = int(datetime.fromisoformat(j["open_utc"]).timestamp() * 1000)
        e, sl, tp = j["entry"], j["sl"], j["tp"]
        rsn, xpx, cms, isc, lastpx, dh = sim_bracket(conn, j["sym"], 1, e, sl, tp, op)
        if isc:
            cens.append(dict(symbol=j["sym"], dur_h=round(dh, 1),
                             mtm=round(pnl_mtm(1, e, lastpx, dh), 2)))
        else:
            closed.append(dict(symbol=j["sym"], reason=rsn, close_ms=cms, dur_h=round(dh, 1),
                               pnl=round(pnl_closed(1, e, xpx, dh), 2)))
    return closed, cens


def policy_C(conn, cs, order, seed=0, use_occ=False):
    """lifecycle actual + competencia causal por 3 cupos. SIN timeout."""
    import random
    rng = random.Random(seed)
    stream = cs["stream"]; iv = cs["interval_ms"]; slots = cs["slots"]
    scan_rank = {s: i for i, s in enumerate(cs["active_order"])}
    occ = {}
    if use_occ:
        p = os.path.join(ROOT, "scratch_occ_mask.json")
        occ = {k: [tuple(x) for x in v] for k, v in json.load(open(p)).items()} if os.path.exists(p) else {}

    def is_occ(sym, ts):
        for o, c in occ.get(sym, ()):
            if o <= ts < c:
                return True
            if o > ts:
                break
        return False

    by_bucket = collections.defaultdict(list)
    for b, sym, e, sl, tp, side, sc in stream:
        by_bucket[b].append((sym, e, sl, tp, side, sc))

    now = WIN_A - (WIN_A % BASE_MS)
    open_tr = {}
    last_day = {}
    closed, cens = [], []
    while now <= KL_END:
        for sym in list(open_tr):
            if open_tr[sym]["close_ms"] <= now:
                t = open_tr.pop(sym)
                (cens if t["_cens"] else closed).append(t)
        occ_now = len(open_tr)
        free = slots - occ_now
        bucket = now - (now % iv)
        cmap = {}
        for kk in (bucket - iv, bucket - 2 * iv, bucket - 3 * iv):
            for c in by_bucket.get(kk, ()):
                cmap.setdefault(c[0], c)
        if cmap:
            day = datetime.utcfromtimestamp(now / 1000).date()
            elig = [c for c in cmap.values()
                    if c[0] not in open_tr and last_day.get(c[0]) != day
                    and not (use_occ and is_occ(c[0], now))]
            if order == "scan":
                elig.sort(key=lambda c: scan_rank.get(c[0], 1 << 30))
            elif order == "sym":
                elig.sort(key=lambda c: c[0])
            elif order == "shuffle":
                rng.shuffle(elig)
            if free > 0:
                for sym, e, sl, tp, side, sc in elig[:free]:
                    rsn, xpx, cms, isc, lastpx, dh = sim_bracket(conn, sym, side, e, sl, tp, now)
                    rec = dict(symbol=sym, reason=rsn, close_ms=cms, dur_h=round(dh, 1),
                               open_ms=now, _cens=isc,
                               pnl=(round(pnl_mtm(side, e, lastpx, dh), 2) if isc
                                    else round(pnl_closed(side, e, xpx, dh), 2)))
                    if isc:
                        rec["mtm"] = rec["pnl"]
                    open_tr[sym] = rec
                    last_day[sym] = day
        now += BASE_MS
    for sym in list(open_tr):
        t = open_tr.pop(sym)
        (cens if t["_cens"] else closed).append(t)
    return closed, cens


def real_asrun():
    J = json.load(open(os.path.join(ROOT, "scratch_caso3_gt.json")))
    pn = [j["pnl"] for j in J]
    pos = sum(p for p in pn if p > 0); neg = -sum(p for p in pn if p < 0)
    dur = [j["dur_h"] for j in J]
    return dict(policy="A. REAL historico (trades.csv)", n=len(J), net=round(sum(pn), 1),
                pf=round(pos / neg, 2), wr=round(100 * sum(1 for p in pn if p > 0) / len(pn)),
                dd="-", tp=sum(1 for j in J if j["real_outcome"] == "TP"),
                sl=sum(1 for j in J if j["real_outcome"] == "SL"),
                dur_med=round(statistics.median(dur), 1), dur_max=round(max(dur), 1),
                ncens="(27 cerrados por timeout en la version vieja)")


def main():
    cs = pickle.load(open(CACHE, "rb"))
    conn = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)

    print("=" * 100)
    print("GOLDEN REPLAY CASO 3 — sin timeout artificial; censurados = OPEN, nunca perdida")
    print("=" * 100)

    A = real_asrun()
    cB, xB = policy_B(conn)
    B = agg(cB, xB, "B. senales reales + lifecycle ACTUAL (sin slots, sin timeout)")

    print(f"\n{'variante':<52}{'clos':>5}{'net':>8}{'PF':>6}{'WR':>5}{'DD':>8}{'tp/sl':>8}{'durMed/Max':>12}{'CENS':>6}")
    def line(m):
        if m.get("n", 0) == 0:
            print(f"{m['policy']:<52}  {m.get('ncens')}"); return
        cens = f"{m['ncens']}"
        dm = f"{m.get('dur_med','-')}/{m.get('dur_max','-')}"
        ts = f"{m.get('tp','-')}/{m.get('sl','-')}"
        print(f"{m['policy']:<52}{m['n']:>5}{m['net']:>8}{m['pf']:>6}{str(m['wr'])+'%':>5}"
              f"{str(m.get('dd','-')):>8}{ts:>8}{dm:>12}{cens:>6}")
    line(A); line(B)

    print("\n--- C. lifecycle ACTUAL + competencia causal por 3 cupos (pool completo, sin timeout) ---")
    for od in ("scan", "sym"):
        cC, xC = policy_C(conn, cs, od)
        line(agg(cC, xC, f"C.{od}"))
    accs = [policy_C(conn, cs, "shuffle", seed=s) for s in range(20)]
    ms = [agg(c, x, "C.shuffle") for c, x in accs]
    nets = sorted(m["net"] for m in ms); pfs = sorted(m["pf"] for m in ms)
    print(f"{'C.shuffle x20  net P5/50/95':<52}{'':>5}{f'{nets[1]:.0f}/{nets[10]:.0f}/{nets[18]:.0f}':>8}"
          f"{f'{pfs[1]:.2f}/{pfs[10]:.2f}/{pfs[18]:.2f}':>14}  net+ {sum(1 for m in ms if m['net']>0)}/20")
    cC, xC = policy_C(conn, cs, "shuffle", seed=0, use_occ=True)
    line(agg(cC, xC, "C.shuffle+occ(x-strat)"))

    # detalle censurados de C.scan
    cC, xC = policy_C(conn, cs, "scan")
    print(f"\n--- CENSURADOS (OPEN al fin del dataset) — politica C.scan ---")
    print(f"  n cerrados: {len(cC)}   n censurados: {len(xC)}")
    if xC:
        cd = sorted(t["dur_h"] for t in xC)
        print(f"  duracion observada censurados (h): min {cd[0]:.0f}  med {statistics.median(cd):.0f}  max {cd[-1]:.0f}")
        print(f"  MTM (informativo, NO realizado) suma: {sum(t['pnl'] for t in xC):+.1f}  "
              f"[{sum(1 for t in xC if t['pnl']>0)} verde / {sum(1 for t in xC if t['pnl']<=0)} rojo]")
    # exposicion
    print(f"\n--- EXPOSICION / cupos (C.scan) ---")
    ev = []
    for t in cC + xC:
        ev.append((t["open_ms"], 1)); ev.append((t["close_ms"], -1))
    ev.sort(); cur = mx = 0
    for _, d in ev:
        cur += d; mx = max(mx, cur)
    print(f"  concurrencia maxima: {mx} / {cs['slots']}   (nunca debe pasar de 3)")

    json.dump({"B": B, "A": A}, open(os.path.join(ROOT, "scratch_golden_caso3.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

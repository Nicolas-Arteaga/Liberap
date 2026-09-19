"""
ROUND 7 — EXPERIMENTO 4 — M18: TOKENIZED-EQUITY PERP vs US CASH-OPEN (arb window).

MECANISMO: los perps de acciones tokenizadas (AAPLUSDT, NVDAUSDT, SPYUSDT, ...)
cotizan 24/7, pero el subyacente real (la accion) SOLO cotiza en el Regular
Trading Hours de EEUU (09:30-16:00 ET = 13:30-20:00 UTC en horario de verano).
Mientras el mercado cash esta CERRADO, el perp driftea con flujo cripto fino y
sin el ancla del subyacente -> acumula una desviacion. Al ABRIR el cash
(13:30 UTC), entran arbitrajistas que pueden hedgear con la accion real (o con
el mecanismo de redencion del token) y FUERZAN la convergencia.

PARTICIPANTE OBLIGADO: market maker / arbitrajista con hedge en la accion real;
el emisor del token via creacion/redencion. Catalizador con timestamp exacto:
la campana de apertura del NYSE.

EVENTO (por simbolo y dia habil D):
  closed_ret = log( open[13:30 UTC en D] / close[20:00 UTC en D-1habil] )
               = cuanto se movio el perp con el cash CERRADO.
  Entrada: open del bar de 13:30 UTC en D.
  Forward: 15/30/60 min y hasta 20:00 UTC (cierre cash).
  Direccion evaluada = -sign(closed_ret)  (apostamos REVERSION / convergencia).
    signo + del retorno reportado = la reversion paga ; signo - = continuacion.

CONTROLES ADVERSARIALES:
  placebo_midday : mismo closed_ret, pero forward medido desde las 17:00 UTC
                   (mitad de sesion, sin catalizador).
  pre_open       : forward medido de 12:30 -> 13:30 UTC (la hora ANTES de abrir).
                   Si la reversion ya ocurre aca, no la dispara la apertura.
  uncond         : retorno medio 13:30->14:30 de TODOS los dias (drift de apertura
                   sistematico, sin condicionar en closed_ret).
  by_bucket      : |closed_ret| en terciles -> la convergencia deberia crecer con
                   el tamano del gap si el mecanismo es real.

VEREDICTO PROMISING (algun horizonte): |after_cost| >= 4bp ; CI excl 0 ;
halves_same_sign ; frac_sym_pos >= 0.55 ; |placebo_midday| y |pre_open| < 0.4*|efecto| ;
monotonia aproximada en by_bucket. Supera costo pero falla criterio -> PARK.
Nada supera costo -> FAILED.

NOTA DST: toda la muestra (2026-05..08) cae en EDT -> open = 13:30 UTC fijo.
"""
import os, sqlite3, json, numpy as np
from datetime import datetime, timezone
from r7_common import agg_pairs

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
BAR = 15 * 60 * 1000
COST_RT_BP = 16.0
OPEN_UTC_MIN = 13 * 60 + 30      # 13:30
CLOSE_UTC_MIN = 20 * 60          # 20:00
MID_UTC_MIN = 17 * 60           # 17:00
PREOPEN_UTC_MIN = 12 * 60 + 30   # 12:30

TICKERS = ['AAOIUSDT','AAPLUSDT','AMDUSDT','AMZNUSDT','ARMUSDT','ASTSUSDT','AVGOUSDT','AXTIUSDT',
           'BABAUSDT','COINUSDT','CRCLUSDT','DELLUSDT','GOOGLUSDT','HIMSUSDT','HOODUSDT','IBMUSDT',
           'INTCUSDT','IRENUSDT','METAUSDT','MSFTUSDT','MSTRUSDT','MUUSDT','NVDAUSDT','OPENUSDT',
           'ORCLUSDT','PLTRUSDT','QCOMUSDT','QQQUSDT','SMCIUSDT','SOXLUSDT','SPXUSDT','SPYUSDT',
           'SQQQUSDT','TSLAUSDT','TZAUSDT','UBERUSDT','UVXYUSDT','XAGUSDT','XAUUSDT']


def main():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    HORS = [1, 2, 4]
    B = {k: {h: [] for h in list(HORS) + ["toclose"]} for k in
         ("real", "plac", "preopen", "uncond")}
    bucket = {b: {h: [] for h in HORS} for b in (0, 1, 2)}
    n_days_total = 0
    used = 0
    for sym in TICKERS:
        r = con.execute("SELECT open_time,open,close FROM klines_clean WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
        if len(r) < 500:
            continue
        used += 1
        t = np.array([x[0] for x in r], np.int64)
        o = np.array([x[1] for x in r], float)
        c = np.array([x[2] for x in r], float)
        idx = {int(v): i for i, v in enumerate(t)}
        minute_of_day = ((t // 60000) % 1440).astype(int)
        day_id = (t // 86400000).astype(int)
        # dias habiles = dias con un bar en 13:30 y otro >= 20:00 el mismo dia
        days = sorted(set(day_id.tolist()))
        prev_close = None; prev_day = None
        # closes por dia a las 20:00
        close2000 = {}
        for D in days:
            m = (day_id == D) & (minute_of_day == CLOSE_UTC_MIN)
            if m.any():
                close2000[D] = c[np.where(m)[0][0]]
        for D in days:
            io = np.where((day_id == D) & (minute_of_day == OPEN_UTC_MIN))[0]
            if len(io) == 0:
                continue
            i_open = io[0]
            # dia habil previo con close 20:00
            pds = [d for d in days if d < D and d in close2000]
            if not pds:
                continue
            Dprev = pds[-1]
            if D - Dprev > 4:      # gap de datos grande -> saltear
                continue
            closed_ret = np.log(o[i_open] / close2000[Dprev])
            if not np.isfinite(closed_ret):
                continue
            n_days_total += 1
            sgn = -np.sign(closed_ret)     # apostamos reversion
            # forward real desde open 13:30
            for h in HORS:
                if i_open + h < len(o):
                    B["real"][h].append((sym, sgn * np.log(o[i_open + h] / o[i_open])))
            # to close 20:00 mismo dia
            ic = np.where((day_id == D) & (minute_of_day == CLOSE_UTC_MIN))[0]
            if len(ic):
                B["real"]["toclose"].append((sym, sgn * np.log(c[ic[0]] / o[i_open])))
            # placebo midday 17:00
            im = np.where((day_id == D) & (minute_of_day == MID_UTC_MIN))[0]
            if len(im):
                j = im[0]
                for h in HORS:
                    if j + h < len(o):
                        B["plac"][h].append((sym, sgn * np.log(o[j + h] / o[j])))
                icl = ic
                if len(icl):
                    B["plac"]["toclose"].append((sym, sgn * np.log(c[icl[0]] / o[j])))
            # pre-open 12:30 -> 13:30
            ip = np.where((day_id == D) & (minute_of_day == PREOPEN_UTC_MIN))[0]
            if len(ip):
                B["preopen"][1].append((sym, sgn * np.log(o[i_open] / o[ip[0]])))
            # uncond: 13:30 -> +1h sin signo-condicion (usamos +1 para no sesgar signo: retorno crudo)
            if i_open + 4 < len(o):
                B["uncond"][4].append((sym, np.log(o[i_open + 4] / o[i_open])))
            # bucket por |closed_ret|
            ab = abs(closed_ret)
        # segundo pase para terciles de |closed_ret| por simbolo
        # (recalculo simple)
    # terciles globales
    con.close()
    allcr = []
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    for sym in TICKERS:
        r = con.execute("SELECT open_time,open,close FROM klines_clean WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
        if len(r) < 500:
            continue
        t = np.array([x[0] for x in r], np.int64); o = np.array([x[1] for x in r], float); c = np.array([x[2] for x in r], float)
        minute_of_day = ((t // 60000) % 1440).astype(int); day_id = (t // 86400000).astype(int)
        days = sorted(set(day_id.tolist()))
        close2000 = {}
        for D in days:
            m = (day_id == D) & (minute_of_day == CLOSE_UTC_MIN)
            if m.any():
                close2000[D] = c[np.where(m)[0][0]]
        for D in days:
            io = np.where((day_id == D) & (minute_of_day == OPEN_UTC_MIN))[0]
            if len(io) == 0:
                continue
            i_open = io[0]
            pds = [d for d in days if d < D and d in close2000]
            if not pds or D - pds[-1] > 4:
                continue
            cr = np.log(o[i_open] / close2000[pds[-1]])
            if np.isfinite(cr):
                allcr.append((sym, D, i_open, cr, o, day_id, minute_of_day, c))
    if allcr:
        crs = np.array([x[3] for x in allcr]); q1, q2 = np.quantile(np.abs(crs), [1 / 3, 2 / 3])
        for sym, D, i_open, cr, o, day_id, mod, c in allcr:
            ab = abs(cr); b = 0 if ab <= q1 else (1 if ab <= q2 else 2)
            sgn = -np.sign(cr)
            for h in HORS:
                if i_open + h < len(o):
                    bucket[b][h].append((sym, sgn * np.log(o[i_open + h] / o[i_open])))
    con.close()

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "symbols_used": used, "n_open_events": n_days_total,
           "params": dict(OPEN_UTC="13:30", COST_RT_BP=COST_RT_BP, HORS=HORS),
           "results": {}, "buckets": {}}
    print(f"perps={used} · eventos de apertura={n_days_total}")

    def line(tag, h):
        R = agg_pairs(B[tag][h])
        return R

    print("\n=== M18  REVERSION EN LA APERTURA DEL CASH (signo + = reversion paga) ===")
    for h in list(HORS) + ["toclose"]:
        R = line("real", h); P = line("plac", h)
        after = round(R["mean_bp"] - np.sign(R["mean_bp"]) * COST_RT_BP, 2) if "mean_bp" in R else None
        out["results"][str(h)] = {"real": R, "placebo_midday": P, "after_cost_bp": after}
        hl = f"{h*15}m" if h != "toclose" else "->20:00"
        print(f"  h={hl:>7}  real={R.get('mean_bp')} bp CI{R.get('ci_bp')} excl0={R.get('ci_excl_0')} "
              f"halves=({R.get('half1_bp')},{R.get('half2_bp')}) symPos={R.get('frac_sym_pos')} conc={R.get('top5_conc')} n={R.get('n')}  "
              f"placebo_midday={P.get('mean_bp')}  after_cost={after}")
    PO = line("preopen", 1); UN = line("uncond", 4)
    out["preopen_1"] = PO; out["uncond_1h"] = UN
    print(f"\n  pre_open (12:30->13:30, signo-cond) = {PO.get('mean_bp')} bp  n={PO.get('n')}")
    print(f"  uncond 13:30->14:30 (retorno CRUDO, sin signo) = {UN.get('mean_bp')} bp  n={UN.get('n')}")
    print("\n  by |closed_ret| tercil (real, signo=reversion):")
    for b in (0, 1, 2):
        row = {}
        for h in HORS:
            R = agg_pairs(bucket[b][h]); row[h] = R.get("mean_bp")
        out["buckets"][b] = row
        print(f"    t{b}: " + "  ".join(f"h{h*15}m={row[h]}bp" for h in HORS))

    path = os.path.join(ROOT, "scratch_r7_m18_rth_open.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(f"\nguardado {path}")


if __name__ == "__main__":
    main()

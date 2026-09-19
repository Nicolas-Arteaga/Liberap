"""
ROUND 18b — DEEP DIVE: capitulación (drop + volumen climax) -> CONTINUACIÓN
(SHORT), el hallazgo más fuerte de R18 Secuencia 2.
Corrige el bug del control "sin climax" (incluía NaN de volp), agrega
TRAIN/VAL/OOS, concentración, placebos (random-timestamp, time-shift +24h),
y sim económica causal con capital <=450 y concurrencia.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r12_smartmoney import pctile_causal
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, mfe_mae, ROLL, HOR, RT_BP
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
DROP_PCT = 0.03; VOL_PCT_THR = 0.90
rng = np.random.default_rng(20260922)


def main():
    print("=== ROUND 18b — DEEP DIVE: capitulación -> SHORT (continuación) ===")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    print(f"universo: {len(P)} símbolos")

    days_all = []
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    for t in P[ref]["t"]:
        days_all.append(datetime.utcfromtimestamp(int(t) / 1000).date())
    days_all = sorted(set(days_all))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}")

    events = []   # (sym, i, day)
    matched_events = []
    for s, d in P.items():
        f = F[s]; n = len(d["c"])
        r1p = f["ret1_pct"]; volp = f["vol_pct"]
        climax = np.isfinite(r1p) & np.isfinite(volp) & (r1p <= DROP_PCT) & (volp >= VOL_PCT_THR)
        matched = np.isfinite(r1p) & np.isfinite(volp) & (r1p <= DROP_PCT) & (volp < 0.5)   # BUG CORREGIDO
        last = -999
        for i in np.where(climax)[0]:
            if i < ROLL or i - last < 4 or i + 1 + max(HOR.values()) >= n:
                continue
            last = i
            events.append((s, i, datetime.utcfromtimestamp(int(d["t"][i]) / 1000).date()))
        last = -999
        for i in np.where(matched)[0]:
            if i < ROLL or i - last < 4 or i + 1 + max(HOR.values()) >= n:
                continue
            last = i
            matched_events.append((s, i, datetime.utcfromtimestamp(int(d["t"][i]) / 1000).date()))
    print(f"eventos climax (drop+vol top10%): {len(events)}   matched (drop, vol bottom50%, corregido): {len(matched_events)}")

    def fwd_short(s, i, hbars):
        d = P[s]; o = d["o"]
        e = i + 1
        if e + hbars >= len(o):
            return None
        return -math.log(o[e + hbars] / o[e])   # SHORT desde open[e]

    print("\n" + "#" * 66 + "\n TRAIN/VAL/OOS — SHORT tras climax, por horizonte\n" + "#" * 66)
    for h_lbl, hb in HOR.items():
        row = {}
        for sgv in ("train", "val", "oos"):
            pairs = [(s, fwd_short(s, i, hb)) for (s, i, dy) in events if seg(dy) == sgv and fwd_short(s, i, hb) is not None]
            R = agg_pairs(pairs); row[sgv] = R
            print(f"  h={h_lbl:>4} {sgv:5s}: {R.get('mean_bp')}bp CI{R.get('ci_bp')} excl0={R.get('ci_excl_0')} "
                  f"symPos={R.get('frac_sym_pos')} conc={R.get('top5_conc')} n={R.get('n')} nS={R.get('n_sym')}")

    print("\n" + "#" * 66 + "\n CONTROL corregido (drop SIN volumen climax) — SHORT\n" + "#" * 66)
    for h_lbl, hb in HOR.items():
        pairs = [(s, fwd_short(s, i, hb)) for (s, i, dy) in matched_events if fwd_short(s, i, hb) is not None]
        R = agg_pairs(pairs)
        print(f"  h={h_lbl:>4}: {R.get('mean_bp')}bp CI{R.get('ci_bp')} excl0={R.get('ci_excl_0')} n={R.get('n')}")

    print("\n" + "#" * 66 + "\n PLACEBOS\n" + "#" * 66)
    # random-timestamp: mismo n de eventos por simbolo, timestamps al azar
    for h_lbl, hb in HOR.items():
        pairs = []
        for s, d in P.items():
            n_ev_sym = sum(1 for (ss, i, dy) in events if ss == s)
            if n_ev_sym == 0:
                continue
            n = len(d["c"])
            idxs = rng.integers(ROLL, n - max(HOR.values()) - 2, size=n_ev_sym)
            for i in idxs:
                v = fwd_short(s, int(i), hb)
                if v is not None:
                    pairs.append((s, v))
        R = agg_pairs(pairs)
        print(f"  PLACEBO random-timestamp  h={h_lbl:>4}: {R.get('mean_bp')}bp CI{R.get('ci_bp')} n={R.get('n')}")
    # time-shift +24h (96 barras)
    for h_lbl, hb in HOR.items():
        pairs = []
        for (s, i, dy) in events:
            d = P[s]
            j = i + 96
            if j + 1 + hb >= len(d["c"]):
                continue
            e = j + 1
            v = -math.log(d["o"][e + hb] / d["o"][e])
            pairs.append((s, v))
        R = agg_pairs(pairs)
        print(f"  PLACEBO time-shift+24h    h={h_lbl:>4}: {R.get('mean_bp')}bp CI{R.get('ci_bp')} n={R.get('n')}")

    print("\n" + "#" * 66 + "\n CONCENTRACIÓN — leave-top-k (h=24h, SHORT)\n" + "#" * 66)
    hb = HOR["24h"]
    by = collections.defaultdict(list)
    for (s, i, dy) in events:
        v = fwd_short(s, i, hb)
        if v is not None:
            by[s].append(v)
    sym_sum = {s: sum(v) for s, v in by.items()}
    order = sorted(sym_sum, key=lambda s: sym_sum[s], reverse=True)
    allv = np.concatenate([np.array(by[s]) for s in by])
    print(f"  símbolos con eventos: {len(by)}  media global={allv.mean()*1e4:+.1f}bp")
    for k in (0, 1, 3, 5, 10, 20):
        drop = set(order[:k])
        v = np.concatenate([np.array(by[s]) for s in by if s not in drop])
        print(f"    -top{k:<3d}: media={v.mean()*1e4:+.1f}bp  n={len(v)}  nSym={len(by)-k}")

    print("\n" + "#" * 66 + "\n SIM ECONÓMICA (entry open[t+1], SHORT, RT=24bp, capital<=450, concurrencia)\n" + "#" * 66)
    for h_lbl, hb in (("12h", HOR["12h"]), ("24h", HOR["24h"])):
        ev_sorted = sorted([(int(P[s]["t"][i + 1]), s, i + 1) for (s, i, dy) in events if i + 1 + hb < len(P[s]["o"])])
        for slots, cap in ((1, 450), (2, 450), (3, 450), (5, 450)):
            notional = cap / slots
            free_at = [0] * slots
            pnl = []
            for (ems, s, ei) in ev_sorted:
                fslot = next((k for k in range(slots) if free_at[k] <= ems), None)
                if fslot is None:
                    continue
                o = P[s]["o"]
                g = -math.log(o[ei + hb] / o[ei]) * 1e4
                net = g - RT_BP
                free_at[fslot] = ems + hb * 15 * 60000
                pnl.append((ems, net))
            if len(pnl) < 10:
                continue
            span_days = (pnl[-1][0] - pnl[0][0]) / 86400000 or 1
            arr = np.array([x[1] for x in pnl])
            usd = arr * notional / 1e4
            net_mo = usd.sum() / (span_days / 30)
            bym = collections.defaultdict(float)
            for (ems, net) in pnl:
                mk = datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")
                bym[mk] += net * notional / 1e4
            months = np.array(sorted(bym.values()))
            eq = np.cumsum(usd); dd = (np.maximum.accumulate(eq) - eq).max()
            flag = "  <<< SUPERA 150" if net_mo >= 150 else ("  (PARK 75-149)" if 75 <= net_mo < 150 else "")
            print(f"  h={h_lbl} slots={slots}x${notional:.0f}: trades_usados={len(pnl)}/{len(ev_sorted)} (capturados/disponibles)  "
                  f"trades/mo={len(pnl)/(span_days/30):.0f}  avg_net={arr.mean():+.1f}bp  med_net={np.median(arr):+.1f}bp  "
                  f"WR={(arr>0).mean():.2f}  PF={arr[arr>0].sum()/max(1e-9,-arr[arr<0].sum()):.2f}  "
                  f"NET/mo=${net_mo:.0f}  maxDD=${dd:.0f}  m[min/med/max]=[{months.min():.0f}/{np.median(months):.0f}/{months.max():.0f}]{flag}")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_events": len(events)}
    json.dump(out, open(os.path.join(ROOT, "scratch_r18b_capitulation.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r18b_capitulation.json")


if __name__ == "__main__":
    main()

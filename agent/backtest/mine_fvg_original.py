"""
Mineria sobre los 257 trades REALES de FVG-15m original (perfil
93f8dbe7-5bbf-4810-99e6-a08145a6e93d, el UNICO que gana de verdad,
+$121.29 -- confirmado 2026-08-05 que todas las variantes/clones
probadas hasta ahora (Pulido, Pulido Long, Gap Chico, etc.) estan en
rojo y restan al agregado).

Objetivo: encontrar una condicion de entrada (presente en el propio
AgentDecisionJson, sin inventar features nuevos) que separe limpio
ganadores de perdedores, siguiendo el mismo metodo de la auditoria del
22/7 (slope_ema50_deg en SHORT). Reportar SIEMPRE el numero real, sin
adornar.
"""
import json

PATH = r"C:\Users\Nicolas\fvg_original_trades.jsonl"


def load():
    rows = []
    with open(PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            idx = line.rfind("|")
            if idx == -1:
                continue
            js, pnl = line[:idx], line[idx + 1:]
            try:
                pnl = float(pnl)
                d = json.loads(js)
            except Exception:
                continue
            cand = d.get("candidate", {})
            fvg = cand.get("agent_audit_context", {}).get("fvg", {})
            snap = d.get("compression_snapshot_at_entry", {})
            btc = d.get("btc_context", {})
            temporal = d.get("temporal_context", {})
            tier = d.get("agent_meta", {}).get("tier")
            rows.append({
                "pnl": pnl,
                "win": pnl > 0,
                "side": cand.get("side"),
                "gap_pct": fvg.get("gap_pct"),
                "tp_distance_pct": fvg.get("tp_distance_pct"),
                "entry_status": fvg.get("entry_status"),
                "slope_ema50_deg": snap.get("slope_ema50_deg"),
                "noise_pct": snap.get("noise_pct"),
                "caida_pct": snap.get("caida_pct"),
                "u_shape_count": snap.get("u_shape_count"),
                "ma99_cluster_dist_pct": snap.get("ma99_cluster_dist_pct"),
                "cement_valid": snap.get("cement_valid"),
                "btc_regime": btc.get("regime"),
                "btc_pct_1h": btc.get("pct_1h"),
                "tier": tier,
                "session": temporal.get("session"),
                "day_of_week": temporal.get("day_of_week"),
                "is_weekend": temporal.get("is_weekend"),
            })
    return rows


def bucket_report(rows, key, buckets):
    print(f"\n== {key} ==")
    for lo, hi, label in buckets:
        sub = [r for r in rows if r[key] is not None and lo <= r[key] < hi]
        if not sub:
            continue
        n = len(sub)
        wr = sum(1 for r in sub if r["win"]) / n * 100
        pnl = sum(r["pnl"] for r in sub)
        print(f"  {label:18s} n={n:4d} WR={wr:5.1f}% PnL=${pnl:8.2f}")


def categorical_report(rows, key):
    print(f"\n== {key} ==")
    vals = sorted(set(r[key] for r in rows if r[key] is not None), key=str)
    for v in vals:
        sub = [r for r in rows if r[key] == v]
        n = len(sub)
        wr = sum(1 for r in sub if r["win"]) / n * 100
        pnl = sum(r["pnl"] for r in sub)
        print(f"  {str(v):18s} n={n:4d} WR={wr:5.1f}% PnL=${pnl:8.2f}")


def main():
    rows = load()
    print(f"Total trades cargados: {len(rows)}")
    total_pnl = sum(r["pnl"] for r in rows)
    total_wr = sum(1 for r in rows if r["win"]) / len(rows) * 100
    print(f"Baseline: WR={total_wr:.1f}% PnL total=${total_pnl:.2f}")

    categorical_report(rows, "side")
    categorical_report(rows, "entry_status")
    categorical_report(rows, "btc_regime")
    categorical_report(rows, "session")
    categorical_report(rows, "tier")
    categorical_report(rows, "cement_valid")
    categorical_report(rows, "is_weekend")

    bucket_report(rows, "gap_pct", [
        (0, 0.3, "<0.3%"), (0.3, 1.0, "0.3-1%"), (1.0, 2.5, "1-2.5%"), (2.5, 100, ">2.5%"),
    ])
    bucket_report(rows, "tp_distance_pct", [
        (0, 8, "<8%"), (8, 15, "8-15%"), (15, 25, "15-25%"), (25, 1000, ">25%"),
    ])
    bucket_report(rows, "slope_ema50_deg", [
        (-1000, -30, "<-30 (caida fuerte)"), (-30, 0, "-30..0"), (0, 30, "0..30"), (30, 1000, ">30 (subida fuerte)"),
    ])
    bucket_report(rows, "noise_pct", [
        (0, 5, "<5%"), (5, 10, "5-10%"), (10, 15, "10-15%"), (15, 1000, ">15%"),
    ])
    bucket_report(rows, "caida_pct", [
        (0, 3, "<3%"), (3, 8, "3-8%"), (8, 15, "8-15%"), (15, 1000, ">15%"),
    ])
    bucket_report(rows, "u_shape_count", [
        (0, 3, "0-2"), (3, 6, "3-5"), (6, 9, "6-8"), (9, 100, "9+"),
    ])
    bucket_report(rows, "ma99_cluster_dist_pct", [
        (0, 2, "<2%"), (2, 5, "2-5%"), (5, 10, "5-10%"), (10, 1000, ">10%"),
    ])
    bucket_report(rows, "btc_pct_1h", [
        (-1000, -0.3, "<-0.3%"), (-0.3, 0.3, "-0.3..0.3%"), (0.3, 1000, ">0.3%"),
    ])


if __name__ == "__main__":
    main()

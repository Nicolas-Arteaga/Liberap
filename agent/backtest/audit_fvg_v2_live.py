"""
Auditoria de los 63 trades reales de "FVG - 15m v2 (filtros minados)"
desde que se activo (2026-08-06) -- confirmar si los 3 filtros
(maxGapPct<=2.5, maxTpDistancePct<=25, maxUShapeCount<9) realmente se
estan respetando en vivo, y comparar contra FVG - 15m original en el
MISMO periodo (para descartar que sea solo mala racha del mercado).
"""
import json

PATH = r"C:\Users\Nicolas\fvg_v2_trades.jsonl"


def load(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            opened_at = parts[-1]
            pnl = parts[-2]
            js = "|".join(parts[:-2])
            try:
                pnl = float(pnl)
                d = json.loads(js)
            except Exception:
                continue
            cand = d.get("candidate", {})
            fvg = cand.get("agent_audit_context", {}).get("fvg", {})
            snap = d.get("compression_snapshot_at_entry", {})
            rows.append({
                "pnl": pnl, "win": pnl > 0, "opened_at": opened_at,
                "gap_pct": fvg.get("gap_pct"),
                "tp_distance_pct": fvg.get("tp_distance_pct"),
                "u_shape_count": snap.get("u_shape_count"),
            })
    return rows


def main():
    rows = load(PATH)
    print(f"Total trades v2: {len(rows)} | rango {rows[0]['opened_at']} -> {rows[-1]['opened_at']}")
    n = len(rows)
    wr = sum(1 for r in rows if r["win"]) / n * 100
    pnl = sum(r["pnl"] for r in rows)
    print(f"WR={wr:.1f}% PnL=${pnl:.2f}")

    print("\n== Violaciones de filtro (deberian ser 0) ==")
    viol_gap = [r for r in rows if r["gap_pct"] is not None and r["gap_pct"] > 2.5]
    viol_tp = [r for r in rows if r["tp_distance_pct"] is not None and r["tp_distance_pct"] > 25]
    viol_u = [r for r in rows if r["u_shape_count"] is not None and r["u_shape_count"] >= 9]
    viol_none = [r for r in rows if r["gap_pct"] is None or r["tp_distance_pct"] is None or r["u_shape_count"] is None]
    print(f"  gap_pct > 2.5:        {len(viol_gap)}")
    print(f"  tp_distance_pct > 25: {len(viol_tp)}")
    print(f"  u_shape_count >= 9:   {len(viol_u)}")
    print(f"  algun campo None:     {len(viol_none)}")

    print("\n== Detalle de cada trade ==")
    for r in rows:
        print(f"  {r['opened_at']} pnl=${r['pnl']:7.2f} gap={r['gap_pct']} tp_dist={r['tp_distance_pct']} u_shape={r['u_shape_count']}")


if __name__ == "__main__":
    main()

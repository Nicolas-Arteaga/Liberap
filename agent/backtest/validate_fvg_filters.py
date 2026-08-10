"""
Validacion con split temporal de los candidatos encontrados en
mine_fvg_original.py sobre los 268 trades reales de FVG-15m original:
excluir u_shape_count>=9, tp_distance_pct>25%, gap_pct>2.5% (por
separado y combinados). Si el efecto no se sostiene en las DOS mitades
(cronologicas) de los datos, se descarta -- mismo criterio que la
auditoria del 22/7.
"""
import json

PATH = r"C:\Users\Nicolas\fvg_original_trades2.jsonl"


def load():
    rows = []
    with open(PATH, encoding="utf-8", errors="replace") as f:
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
                "pnl": pnl,
                "win": pnl > 0,
                "opened_at": opened_at,
                "gap_pct": fvg.get("gap_pct"),
                "tp_distance_pct": fvg.get("tp_distance_pct"),
                "u_shape_count": snap.get("u_shape_count"),
            })
    rows.sort(key=lambda r: r["opened_at"])
    return rows


def summarize(label, sub):
    n = len(sub)
    if n == 0:
        print(f"    {label:30s} n=0")
        return
    wr = sum(1 for r in sub if r["win"]) / n * 100
    pnl = sum(r["pnl"] for r in sub)
    print(f"    {label:30s} n={n:4d} WR={wr:5.1f}% PnL=${pnl:8.2f}")


def excluded(r, u_cut, tp_cut, gap_cut):
    if u_cut and r["u_shape_count"] is not None and r["u_shape_count"] >= 9:
        return True
    if tp_cut and r["tp_distance_pct"] is not None and r["tp_distance_pct"] > 25:
        return True
    if gap_cut and r["gap_pct"] is not None and r["gap_pct"] > 2.5:
        return True
    return False


def run_variant(rows, name, u_cut, tp_cut, gap_cut):
    print(f"\n=== {name} ===")
    half = len(rows) // 2
    halves = [("1ra mitad (cronologica)", rows[:half]), ("2da mitad (cronologica)", rows[half:]), ("TOTAL", rows)]
    for label, sub in halves:
        base = sub
        filtered = [r for r in sub if not excluded(r, u_cut, tp_cut, gap_cut)]
        summarize(f"{label} SIN filtro", base)
        summarize(f"{label} CON filtro", filtered)


def main():
    rows = load()
    print(f"Total trades: {len(rows)} | rango: {rows[0]['opened_at']} -> {rows[-1]['opened_at']}")

    run_variant(rows, "Excluir u_shape_count>=9", True, False, False)
    run_variant(rows, "Excluir tp_distance_pct>25%", False, True, False)
    run_variant(rows, "Excluir gap_pct>2.5%", False, False, True)
    run_variant(rows, "Excluir los 3 combinados", True, True, True)


if __name__ == "__main__":
    main()

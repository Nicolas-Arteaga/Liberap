"""
Meta-labeling v2: mismo metodo que meta_labeling_fvg.py pero con TODOS
los trades reales de TODAS las variantes de FVG (Original, Pulido,
Pulido V2, Pulido Long, Gap Chico, v2) -- 1766 filas crudas en vez de
316, mismo espacio de features porque comparten el mismo detector base
(_build_fvg_candidate). Deduplicado por (symbol, side, ventana de 15min)
para no contar el mismo evento real de mercado varias veces solo porque
mas de un perfil lo tomo el mismo ciclo -- eso inflaria la muestra de
forma artificial (pseudo-replicacion).

Uso: python -m backtest.meta_labeling_fvg_v2   (desde agent/)
"""
import json
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

PATH = r"C:\Users\Nicolas\fvg_all_variants.jsonl"

FEATURES = [
    "gap_pct", "tp_distance_pct", "u_shape_count", "side",
    "slope_ema50", "caida_pct", "noise_pct", "ma99_cluster_dist_pct",
    "btc_pct_1h", "btc_pct_15m",
]


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
            btc = d.get("btc_context", {})
            symbol = cand.get("symbol")
            side = cand.get("side")
            if symbol is None or side is None:
                continue
            rows.append({
                "pnl": pnl, "win": 1 if pnl > 0 else 0, "opened_at": opened_at,
                "symbol": symbol, "side": side,
                "gap_pct": fvg.get("gap_pct"), "tp_distance_pct": fvg.get("tp_distance_pct"),
                "u_shape_count": snap.get("u_shape_count"),
                "slope_ema50": snap.get("slope_ema50_deg"), "caida_pct": snap.get("caida_pct"),
                "noise_pct": snap.get("noise_pct"), "ma99_cluster_dist_pct": snap.get("ma99_cluster_dist_pct"),
                "btc_pct_1h": btc.get("pct_1h"), "btc_pct_15m": btc.get("pct_15m"),
            })
    rows.sort(key=lambda r: r["opened_at"])

    # Dedup: mismo simbolo+side+ventana de 15 min = mismo evento real de
    # mercado tomado por mas de un perfil ese ciclo -- nos quedamos con 1.
    from datetime import datetime
    seen = set()
    deduped = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(r["opened_at"].replace("+00", "")[:19])
            bucket = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        except Exception:
            bucket = r["opened_at"]
        key = (r["symbol"], r["side"], bucket)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def to_matrix(rows):
    X, y, pnl = [], [], []
    for r in rows:
        vec = [r[f] if r[f] is not None else 0.0 for f in FEATURES]
        X.append(vec)
        y.append(r["win"])
        pnl.append(r["pnl"])
    return np.array(X, dtype=float), np.array(y, dtype=float), np.array(pnl, dtype=float)


def kelly_fraction(p_win, avg_win_pct, avg_loss_pct, cap=1.0, floor=0.1):
    if avg_win_pct <= 0 or avg_loss_pct <= 0:
        return 0.5
    q = 1 - p_win
    f = p_win / avg_loss_pct - q / avg_win_pct
    return max(floor, min(cap, f))


def main():
    rows = load()
    print(f"Total (deduplicado): {len(rows)} trades reales | rango {rows[0]['opened_at'][:10]} -> {rows[-1]['opened_at'][:10]}\n")

    half = len(rows) // 2
    train, test = rows[:half], rows[half:]
    print(f"Train: {len(train)} | Test (nunca visto): {len(test)}\n")

    X_train, y_train, pnl_train = to_matrix(train)
    X_test, y_test, pnl_test = to_matrix(test)

    scaler = StandardScaler().fit(X_train)
    Xs_train = scaler.transform(X_train)
    Xs_test = scaler.transform(X_test)

    model = LogisticRegression(C=0.5, max_iter=1000, class_weight="balanced")
    model.fit(Xs_train, y_train)
    p_test = model.predict_proba(Xs_test)[:, 1]

    wins_train = [r["pnl"] for r in train if r["pnl"] > 0]
    losses_train = [abs(r["pnl"]) for r in train if r["pnl"] <= 0]
    avg_win = np.mean(wins_train) / 150.0
    avg_loss = np.mean(losses_train) / 150.0

    baseline_test_pnl = sum(pnl_test)
    print(f"BASELINE test (margen fijo, sin modelo): PnL=${baseline_test_pnl:.2f} WR={y_test.mean()*100:.1f}% ({len(test)} trades)\n")

    for cap in (0.7, 1.0):
        for floor in (0.1, 0.3, 0.5):
            total = sum(r["pnl"] * kelly_fraction(p_test[i], avg_win, avg_loss, cap=cap, floor=floor) for i, r in enumerate(test))
            print(f"Kelly (cap={cap}, floor={floor}): PnL test=${total:.2f}")

    order = np.argsort(p_test)
    n = len(test)
    for frac, label in ((0.2, "20%"), (0.3, "30%"), (0.5, "50%")):
        k = int(n * frac)
        bottom = order[:k]
        top = order[-k:]
        print(f"\nBottom {label} prob: WR real={y_test[bottom].mean()*100:.1f}% PnL=${pnl_test[bottom].sum():.2f} (n={k})")
        print(f"Top {label} prob:    WR real={y_test[top].mean()*100:.1f}% PnL=${pnl_test[top].sum():.2f} (n={k})")

    coefs = dict(zip(FEATURES, model.coef_[0]))
    print("\nPesos del modelo (features estandarizadas):")
    for f, c in sorted(coefs.items(), key=lambda x: -abs(x[1])):
        print(f"  {f:24s} {c:+.3f}")


if __name__ == "__main__":
    main()

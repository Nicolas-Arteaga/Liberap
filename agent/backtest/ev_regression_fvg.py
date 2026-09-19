"""
Herramienta v2, basada en el hallazgo real: optimizar por probabilidad de
ganar (win rate) apunta para el lado CONTRARIO en FVG-15m, porque la
ganancia vive en pocos outliers grandes, no en acertar seguido (ver
meta_labeling_fvg_v2.py: top-20% probabilidad = PEOR PnL que bottom-20%).

En vez de CLASIFICAR ganador/perdedor, este modelo hace REGRESION directa
sobre el PnL en dolares -- persigue magnitud esperada, no acierto. Mismos
features, mismo dataset deduplicado (1657 trades reales, todas las
variantes de FVG), mismo walk-forward real (entrena en la mitad vieja,
prueba en la mitad nunca vista).

Sizing: margen proporcional al PnL esperado normalizado (nunca negativo,
nunca cero -- entre floor y cap), no un filtro binario.

Uso: python -m backtest.ev_regression_fvg   (desde agent/)
"""
import json
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor
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
                "pnl": pnl, "opened_at": opened_at, "symbol": symbol, "side": side,
                "gap_pct": fvg.get("gap_pct"), "tp_distance_pct": fvg.get("tp_distance_pct"),
                "u_shape_count": snap.get("u_shape_count"),
                "slope_ema50": snap.get("slope_ema50_deg"), "caida_pct": snap.get("caida_pct"),
                "noise_pct": snap.get("noise_pct"), "ma99_cluster_dist_pct": snap.get("ma99_cluster_dist_pct"),
                "btc_pct_1h": btc.get("pct_1h"), "btc_pct_15m": btc.get("pct_15m"),
            })
    rows.sort(key=lambda r: r["opened_at"])
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
    X, pnl = [], []
    for r in rows:
        vec = [r[f] if r[f] is not None else 0.0 for f in FEATURES]
        X.append(vec)
        pnl.append(r["pnl"])
    return np.array(X, dtype=float), np.array(pnl, dtype=float)


def size_from_pred(pred, lo, hi, floor=0.2, cap=1.0):
    """Normaliza la prediccion a [floor, cap] segun su posicion en el rango del train."""
    if hi <= lo:
        return 0.5
    norm = (pred - lo) / (hi - lo)
    norm = max(0.0, min(1.0, norm))
    return floor + norm * (cap - floor)


def evaluate(name, model, X_train, y_train, X_test, y_test, test_rows):
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    lo, hi = np.percentile(model.predict(X_train), [5, 95])

    baseline = sum(r["pnl"] for r in test_rows)
    sized_total = 0.0
    for i, r in enumerate(test_rows):
        f = size_from_pred(pred[i], lo, hi)
        sized_total += r["pnl"] * f

    order = np.argsort(pred)
    n = len(test_rows)
    bottom30 = order[: int(n * 0.3)]
    top30 = order[-int(n * 0.3):]
    pnl_bottom = sum(test_rows[i]["pnl"] for i in bottom30)
    pnl_top = sum(test_rows[i]["pnl"] for i in top30)

    print(f"\n=== {name} ===")
    print(f"BASELINE (margen fijo):        PnL=${baseline:.2f}")
    print(f"SIZING por EV predicho:        PnL=${sized_total:.2f}")
    print(f"Bottom 30% EV predicho: PnL=${pnl_bottom:.2f} (n={len(bottom30)})")
    print(f"Top 30% EV predicho:    PnL=${pnl_top:.2f} (n={len(top30)})")
    return sized_total


def main():
    rows = load()
    half = len(rows) // 2
    train, test = rows[:half], rows[half:]
    print(f"Total deduplicado: {len(rows)} | Train={len(train)} | Test (nunca visto)={len(test)}")

    X_train, y_train = to_matrix(train)
    X_test, y_test = to_matrix(test)
    scaler = StandardScaler().fit(X_train)
    Xs_train, Xs_test = scaler.transform(X_train), scaler.transform(X_test)

    evaluate("Ridge Regression (lineal, EV)", Ridge(alpha=5.0), Xs_train, y_train, Xs_test, y_test, test)
    evaluate("Gradient Boosting (no lineal, EV)",
             GradientBoostingRegressor(n_estimators=80, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=42),
             X_train, y_train, X_test, y_test, test)


if __name__ == "__main__":
    main()

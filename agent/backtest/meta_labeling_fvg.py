"""
Meta-labeling (Lopez de Prado) sobre los 316 trades reales de FVG-15m
original: un MODELO SECUNDARIO (regresion logistica) que aprende, de los
datos, la probabilidad de que una señal ya generada por FVG-15m gane --
no reemplaza la señal primaria (direccion/entrada), solo decide CUANTO
apostarle. Entrenado con walk-forward real (primera mitad cronologica
entrena, segunda mitad -- nunca vista -- se evalua) para evitar el mismo
hindsight bias que ya nos quemo 4 veces con filtros a mano.

Sizing: fraccion de Kelly acotada, margen = base * kelly_fraction (nunca
0, nunca mas que el margen base) -- igual espiritu que el multiplicador
dinamico ya cableado en risk_manager.py/verge_agent.py, pero la señal de
calidad ahora sale de un modelo real, no de 3 umbrales elegidos a mano.

Uso: python -m backtest.meta_labeling_fvg   (desde agent/)
"""
import json
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

PATH = r"C:\Users\Nicolas\fvg_orig_all.jsonl"

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
            rows.append({
                "pnl": pnl, "win": 1 if pnl > 0 else 0, "opened_at": opened_at,
                "gap_pct": fvg.get("gap_pct"), "tp_distance_pct": fvg.get("tp_distance_pct"),
                "u_shape_count": snap.get("u_shape_count"), "side": cand.get("side"),
                "slope_ema50": snap.get("slope_ema50_deg"), "caida_pct": snap.get("caida_pct"),
                "noise_pct": snap.get("noise_pct"), "ma99_cluster_dist_pct": snap.get("ma99_cluster_dist_pct"),
                "btc_pct_1h": btc.get("pct_1h"), "btc_pct_15m": btc.get("pct_15m"),
            })
    rows.sort(key=lambda r: r["opened_at"])
    return rows


def to_matrix(rows):
    X, y, pnl = [], [], []
    for r in rows:
        vec = [r[f] if r[f] is not None else 0.0 for f in FEATURES]
        X.append(vec)
        y.append(r["win"])
        pnl.append(r["pnl"])
    return np.array(X, dtype=float), np.array(y, dtype=float), np.array(pnl, dtype=float)


def kelly_fraction(p_win, avg_win_pct, avg_loss_pct, cap=1.0, floor=0.1):
    """Kelly clasico: f* = p/L - q/W (L,W en fraccion perdida/ganada por trade)."""
    if avg_win_pct <= 0 or avg_loss_pct <= 0:
        return 0.5
    q = 1 - p_win
    f = p_win / avg_loss_pct - q / avg_win_pct
    return max(floor, min(cap, f))


def main():
    rows = load()
    half = len(rows) // 2
    train, test = rows[:half], rows[half:]
    print(f"Train (1ra mitad cronologica): {len(train)} trades | Test (2da mitad, NUNCA vista): {len(test)} trades\n")

    X_train, y_train, pnl_train = to_matrix(train)
    X_test, y_test, pnl_test = to_matrix(test)

    scaler = StandardScaler().fit(X_train)
    Xs_train = scaler.transform(X_train)
    Xs_test = scaler.transform(X_test)

    model = LogisticRegression(C=0.5, max_iter=1000, class_weight="balanced")
    model.fit(Xs_train, y_train)

    p_test = model.predict_proba(Xs_test)[:, 1]  # prob de ganar, segun el modelo, en datos NUNCA vistos

    # Estadisticas de payoff reales del train (para Kelly)
    wins_train = [r["pnl"] for r in train if r["pnl"] > 0]
    losses_train = [abs(r["pnl"]) for r in train if r["pnl"] <= 0]
    avg_win = np.mean(wins_train) / 150.0  # como fraccion del margen $150
    avg_loss = np.mean(losses_train) / 150.0
    print(f"Payoff (train): avg_win=${np.mean(wins_train):.2f} avg_loss=${np.mean(losses_train):.2f}\n")

    print(f"{'Umbral prob':>12s} | {'AUC-like split':>0s}")
    baseline_test_pnl = sum(pnl_test)
    print(f"BASELINE test (margen fijo \$150, sin meta-label): PnL=${baseline_test_pnl:.2f} ({len(test)} trades)\n")

    for cap in (0.7, 1.0):
        for floor in (0.1, 0.3, 0.5):
            total = 0.0
            for i, r in enumerate(test):
                f = kelly_fraction(p_test[i], avg_win, avg_loss, cap=cap, floor=floor)
                total += r["pnl"] * f
            print(f"Kelly (cap={cap}, floor={floor}): PnL test=${total:.2f}")

    print("\nDistribucion de probabilidad predicha (test, out-of-sample):")
    print(f"  min={p_test.min():.3f} max={p_test.max():.3f} media={p_test.mean():.3f}")
    print(f"  WR real en test: {y_test.mean()*100:.1f}%")

    # Separar test en dudosas (p baja) vs buenas (p alta) segun el modelo, y ver si el modelo separa algo real
    order = np.argsort(p_test)
    n = len(test)
    bottom30 = order[: int(n * 0.3)]
    top30 = order[-int(n * 0.3):]
    wr_bottom = y_test[bottom30].mean() * 100
    wr_top = y_test[top30].mean() * 100
    pnl_bottom = pnl_test[bottom30].sum()
    pnl_top = pnl_test[top30].sum()
    print(f"\nBottom 30% prob (modelo dice 'mala'): WR real={wr_bottom:.1f}% PnL=${pnl_bottom:.2f}")
    print(f"Top 30% prob    (modelo dice 'buena'): WR real={wr_top:.1f}% PnL=${pnl_top:.2f}")


if __name__ == "__main__":
    main()

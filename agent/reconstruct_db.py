"""
reconstruct_db.py — reconstrucción de la DB Verge tras el reset accidental de
Docker Desktop (2026-09-05) que borró todos los volúmenes.

FUENTE: agent/data/trades.csv (log del agente en disco, sobrevivió).
LIMITACIONES (documentadas, NO ocultadas):
  * trades.csv es PARCIAL (ej: 70/113 trades de MA Slope Caso 2).
  * NO tiene OpenedAt/ClosedAt exactos (solo `date` = hora de señal + duration_h).
  * NO tiene AgentDecisionJson, ExitReason, fees ni funding reales.
  * `result` (WIN/LOSS) tiene ~2% de ruido -> se usa `pnl_usd` como verdad.
  * Las estrategias Nexus/SCAR van todas juntas como "Nexus" (sin sub-tipo).
  * Los PatternParamsJson (salvo MA Slope Caso 2) NO se recuperaron -> aproximados.

=> La DB reconstruida sirve para que la app funcione y para tener un historial
   aproximado. NO es ground truth de gold-standard para Phase 3.

  python reconstruct_db.py --dry     # genera reconstruct.sql, no aplica
  python reconstruct_db.py           # genera y aplica via docker exec psql
"""
import os, sys, csv, re, json, uuid, subprocess, datetime as dt

HERE = os.path.dirname(__file__)
CSV = os.path.join(HERE, "data", "trades.csv")
SQL = os.path.join(HERE, "reconstruct.sql")
USER_ID = "3a238694-8be5-ad38-5ebf-c49d40759367"  # admin (seed del migrator)

# MA Slope Caso 2 -- config REAL recuperada textual de los logs de gate v1/v2.
CASO2_PARAMS = ('{"timeframe": "1h", "order": {"ma7VsMa25": "less", "ma7VsMa50": "less", "ma7VsMa99": "greater"}, '
    '"slope": {"targetMa": "ma7", "windowCandles": 3, "currentOp": null, "currentDeg": null, "priorOp": null, "priorDeg": null}, '
    '"touch": {"enabled": false, "targetMa": "ma25", "tolerancePct": 0.3, "side": "fromBelow", "requireCloseStaysOriginalSide": true}, '
    '"distanceBetweenMas": {"enabled": true, "maA": "ma7", "maB": "ma99", "maxPct": 0.5}, '
    '"contextSlope": {"enabled": true, "targetMa": "ma99", "windowCandles": 12, "op": "gte", "deg": -0.1}, '
    '"peakProximity": {"enabled": false, "type": "recentHigh", "lookbackCandles": 10, "tolerancePct": 1.0}, '
    '"exit": {"slReference": "recentLow", "slLookbackCandles": 10, "slBufferPct": 1.5, "tpMinPct": 8.0}}')


def strat_of(row):
    er = row.get("entry_reason", "") or ""
    m = re.search(r"\[STRAT:\s*([^\]]+)\]", er)
    return m.group(1).strip() if m else (row.get("source") or "Unknown").strip()


def stype(name):
    n = name.lower()
    if n.startswith("ma slope") or n == "ma pattern":
        return "MaGeometry"
    if n.startswith("fvg"):
        return "FVG"
    if "adn" in n or "compresion" in n:
        return "AdnCompression"
    return "Generic"


def params_for(name):
    """PatternParamsJson best-effort. Caso 2 = real; el resto aproximado."""
    if name == "MA Slope Caso 2":
        return CASO2_PARAMS, True
    st = stype(name)
    if st == "MaGeometry":
        tf = "15m" if "(15m)" in name else "1h"
        tpmin = 3.0 if "Pulido" in name else 10.0
        return ('{"timeframe": "%s", "exit": {"slReference": "recentLow", "slLookbackCandles": 10, '
                '"slBufferPct": 1.5, "tpMinPct": %s}, "_reconstruido": true}' % (tf, tpmin)), False
    if st == "FVG":
        tf = "1m" if "1m" in name else ("5m" if "5m" in name else "15m")
        return '{"timeframe": "%s", "_reconstruido": true}' % tf, False
    if st == "AdnCompression":
        return '{"timeframe": "5m", "_reconstruido": true}', False
    return None, False


def esc(s):
    return s.replace("'", "''") if s else s


def exit_reason(entry, tp, sl, exitpx, pnl):
    try:
        e, t, s, x = float(entry), float(tp), float(sl), float(exitpx)
    except Exception:
        return "unknown"
    dt_tp, dt_sl = abs(x - t), abs(x - s)
    if dt_tp < dt_sl and float(pnl) > 0:
        return "tp_hit"
    if dt_sl < dt_tp:
        return "sl_hit"
    return "timeout"


def main():
    dry = "--dry" in sys.argv
    rows = list(csv.DictReader(open(CSV, encoding="utf-8", errors="replace")))
    strategies = sorted(set(strat_of(r) for r in rows))

    out = []
    out.append("BEGIN;")
    out.append("-- StrategyProfiles reconstruidos (2026-09-05, tras reset de Docker)")
    pid = {}
    for name in strategies:
        pid[name] = str(uuid.uuid4())
        pj, real = params_for(name)
        pj_sql = "NULL" if pj is None else f"'{esc(pj)}'"
        desc = ("Config REAL recuperada de logs." if (name == "MA Slope Caso 2")
                else "RECONSTRUIDO 2026-09-05 tras perdida de datos - config APROXIMADA, revisar/re-tunear.")
        allow_long = "true"
        allow_short = "false" if name.startswith("MA Slope") else "true"
        tpm = 3.0
        slm = 0.8 if name == "MA Slope Caso 2" else 1.0
        minrr = 3.0
        mtdc = 96 if stype(name) == "MaGeometry" else (60 if stype(name) == "FVG" else 16)
        out.append(
            f"INSERT INTO \"StrategyProfiles\" (\"Id\",\"UserId\",\"Name\",\"IsActive\","
            f"\"MinConfluenceScore\",\"MinNexusConfidence\",\"MaxRsiLong\",\"MinRsiShort\","
            f"\"MaxMa7DistancePct\",\"AllowedSources\",\"AllowLong\",\"AllowShort\",\"MarginPerTrade\","
            f"\"TpMultiplier\",\"SlMultiplier\",\"MinRR\",\"MaxOpenPositions\",\"MaxTradeDurationCandles\","
            f"\"ExtraProperties\",\"ConcurrencyStamp\",\"CreationTime\",\"IsDeleted\",\"Color\",\"Description\","
            f"\"PatternParamsJson\",\"StrategyType\") VALUES ("
            f"'{pid[name]}','{USER_ID}','{esc(name)}',false,60,60,75,25,3,'reconstructed',"
            f"{allow_long},{allow_short},150,{tpm},{slm},{minrr},3,{mtdc},"
            f"'{{}}','{uuid.uuid4().hex[:32]}',now(),false,'','{esc(desc)}',{pj_sql},'{stype(name)}');")

    out.append("-- SimulatedTrades reconstruidos desde trades.csv (PARCIAL, sin OpenedAt exacto)")
    n_ins = 0
    for r in rows:
        try:
            entry = float(r["entry"]); exitpx = float(r["exit_price"]); pnl = float(r["pnl_usd"])
        except Exception:
            continue
        sl = r.get("sl") or "0"; tp = r.get("tp") or "0"
        d = r["date"].strip()
        try:
            opened = dt.datetime.strptime(d, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        dur = float(r.get("duration_h") or 0)
        closed = opened + dt.timedelta(hours=dur)
        side = 1 if (r.get("direction", "").upper() in ("BEARISH", "SHORT", "SELL")) else 0
        er = exit_reason(entry, tp, sl, exitpx, pnl)
        status = 1 if er == "tp_hit" else 2
        name = strat_of(r)
        qty = 150.0 / entry if entry else 0
        out.append(
            f"INSERT INTO \"SimulatedTrades\" (\"Id\",\"UserId\",\"Symbol\",\"Side\",\"Leverage\",\"Size\","
            f"\"Amount\",\"EntryPrice\",\"MarkPrice\",\"LiquidationPrice\",\"Margin\",\"MarginRate\","
            f"\"UnrealizedPnl\",\"ROIPercentage\",\"Status\",\"ClosePrice\",\"RealizedPnl\",\"EntryFee\","
            f"\"ExitFee\",\"TotalFundingPaid\",\"OpenedAt\",\"ClosedAt\",\"SlPrice\",\"TpPrice\","
            f"\"ExitReason\",\"StrategyProfileId\",\"Exchange\",\"ExtraProperties\",\"ConcurrencyStamp\","
            f"\"CreationTime\",\"IsDeleted\") VALUES ("
            f"'{uuid.uuid4()}','{USER_ID}','{esc(r['symbol'])}',{side},1,{qty:.8f},150,{entry},{exitpx},0,150,0.01,"
            f"0,0,{status},{exitpx},{pnl},0.06,0.06,0,'{opened.isoformat()}Z','{closed.isoformat()}Z',"
            f"{sl},{tp},'{er}','{pid[name]}','Binance',"
            f"'{{\"reconstructed\":\"trades.csv 2026-09-05\"}}','{uuid.uuid4().hex[:32]}',now(),false);")
        n_ins += 1

    out.append("COMMIT;")
    open(SQL, "w", encoding="utf-8").write("\n".join(out))
    print(f"[reconstruct] {len(strategies)} StrategyProfiles + {n_ins} SimulatedTrades -> {SQL}")
    if dry:
        print("[reconstruct] --dry: no se aplico"); return
    p = subprocess.run(["docker", "exec", "-i", "verge-db", "psql", "-U", "postgres", "-d", "Verge"],
                       stdin=open(SQL, "rb"), capture_output=True)
    print(p.stdout.decode()[-2000:])
    if p.returncode != 0:
        print("STDERR:", p.stderr.decode()[-3000:])
    else:
        print("[reconstruct] aplicado OK")


if __name__ == "__main__":
    main()

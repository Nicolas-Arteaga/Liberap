import os
import csv
import json
import config

class AuditEngine:
    def __init__(self):
        self.csv_file = config.TRADES_LOG_FILE
        self.positions_file = config.POSITIONS_FILE

    def get_summary(self):
        trades = self._read_csv()
        total_trades = len(trades)
        wins = sum(1 for t in trades if t["result"] == "WIN")
        pnl_total = sum(float(t["pnl_usd"]) for t in trades if t["pnl_usd"])
        
        win_rate = 0.0
        if total_trades > 0:
            win_rate = round((wins / total_trades) * 100, 1)

        # balance is Virtual Capital + PnL
        balance = config.VIRTUAL_CAPITAL_BASE + pnl_total

        return {
            "balance": round(balance, 2),
            "winRate": win_rate,
            "trades": total_trades,
            "pnlTotal": round(pnl_total, 2)
        }

    def get_recent_trades(self, limit=10):
        trades = self._read_csv()
        # sort by date desc
        trades.reverse()
        return trades[:limit]

    def get_top_symbols(self, limit=5):
        trades = self._read_csv()
        stats = {}
        for t in trades:
            sym = t["symbol"]
            if sym not in stats:
                stats[sym] = {"trades": 0, "wins": 0, "pnl": 0.0}
            stats[sym]["trades"] += 1
            if t["result"] == "WIN":
                stats[sym]["wins"] += 1
            stats[sym]["pnl"] += float(t["pnl_usd"] or 0)
        
        results = []
        for sym, data in stats.items():
            wr = round((data["wins"] / data["trades"]) * 100, 1) if data["trades"] > 0 else 0.0
            results.append({
                "symbol": sym,
                "winRate": wr,
                "pnl": round(data["pnl"], 2),
                "trades": data["trades"]
            })
            
        results.sort(key=lambda x: x["pnl"], reverse=True)
        return results[:limit]

    def get_strategy_stats(self):
        trades = self._read_csv()
        
        def calculate_strat(source_filter):
            filtered = [t for t in trades if source_filter(t["source"])]
            if not filtered:
                return {"winRate": 0.0, "pnl": 0.0, "trades": 0, "promWin": 0.0, "promLoss": 0.0}
            
            wins = [float(t["pnl_usd"]) for t in filtered if t["result"] == "WIN"]
            losses = [float(t["pnl_usd"]) for t in filtered if t["result"] == "LOSS"]
            
            wr = round((len(wins) / len(filtered)) * 100, 1)
            pnl = sum(wins) + sum(losses)
            prom_win = sum(wins) / len(wins) if wins else 0
            prom_loss = sum(losses) / len(losses) if losses else 0
            
            return {
                "winRate": wr,
                "pnl": round(pnl, 2),
                "trades": len(filtered),
                "promWin": round(prom_win, 2),
                "promLoss": round(prom_loss, 2)
            }

        scar_stats = calculate_strat(lambda s: s == "SCAR")
        nexus_stats = calculate_strat(lambda s: s == "Nexus")
        confluence_stats = calculate_strat(lambda s: s == "SCAR+Nexus")
        
        # Fake TPSL stats for now based on global stats
        global_wins = sum(1 for t in trades if t["result"] == "WIN")
        tpsl_stats = {
            "effectiveness": round((global_wins / max(1, len(trades))) * 100, 1),
            "trades": len(trades),
            "tpRate": round((global_wins / max(1, len(trades))) * 100, 1),
            "slRate": round(((len(trades) - global_wins) / max(1, len(trades))) * 100, 1),
            "rr": 1.5
        }

        return {
            "scar": scar_stats,
            "nexus": nexus_stats,
            "confluence": confluence_stats,
            "tpsl": tpsl_stats
        }

    def get_open_positions(self):
        if not os.path.exists(self.positions_file):
            return []
        try:
            with open(self.positions_file, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _read_csv(self):
        if not os.path.exists(self.csv_file):
            return []
        trades = []
        try:
            with open(self.csv_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append(row)
        except Exception:
            pass
        return trades

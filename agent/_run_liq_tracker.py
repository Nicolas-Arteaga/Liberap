"""Runner standalone del liquidation_tracker para research. UTF-8 forzado."""
import sys, logging

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s",
                    stream=sys.stdout)

if __name__ == "__main__":
    from liquidation_tracker import run_liquidation_capture
    run_liquidation_capture(agent_log=logging.getLogger("LiqTracker").info)

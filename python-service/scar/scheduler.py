from apscheduler.schedulers.background import BackgroundScheduler
from .learn import evaluate_predictions
from .detector import scan_symbols
import logging

logger = logging.getLogger("SCAR_SCHEDULER")

TOP_SYMBOLS = [
    'BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','ADAUSDT','DOGEUSDT','AVAXUSDT',
    'DOTUSDT','MATICUSDT','LINKUSDT','LTCUSDT','UNIUSDT','ATOMUSDT','XLMUSDT','ETCUSDT',
    'TRXUSDT','NEARUSDT','FILUSDT','AAVEUSDT','ALGOUSDT','VETUSDT','ICPUSDT','APTUSDT'
]

def scan_top_symbols():
    logger.info("🌊 SCAR Scheduler: Starting background scan for top symbols...")
    scan_symbols(TOP_SYMBOLS)
    logger.info("🌊 SCAR Scheduler: Background scan complete.")

scheduler = BackgroundScheduler()

def start_scheduler():
    if not scheduler.running:
        # Evaluate old predictions once a day
        scheduler.add_job(evaluate_predictions, 'interval', hours=24, id='scar_eval', replace_existing=True)
        # Scan top symbols every 6 hours to keep the radar fresh
        scheduler.add_job(scan_top_symbols, 'interval', hours=6, id='scar_scan', replace_existing=True)
        # Run one scan immediately at startup
        scheduler.add_job(scan_top_symbols, id='scar_initial_scan')
        
        scheduler.start()
        logger.info("⏱️ SCAR background scheduler started (Eval: 24h, Scan: 6h).")

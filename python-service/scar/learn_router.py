from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
import logging
from datetime import datetime, timezone

from . import learn, data_store

logger = logging.getLogger("SCAR_LEARN_ROUTER")

router = APIRouter(prefix="/learn", tags=["SCAR - Learning & Feedback"])

class FeedbackRequest(BaseModel):
    result: str  # "hit" | "false_alarm" | "ignore"

@router.get("/predictions")
def api_get_predictions(status: Optional[str] = None, limit: int = 50):
    return learn.get_predictions(status, limit)

@router.get("/accuracy")
def api_get_accuracy(symbol: Optional[str] = None):
    return learn.get_accuracy_metrics(symbol)

@router.get("/adjustments")
def api_get_adjustments(limit: int = 20):
    return learn.get_adjustments(limit)

@router.post("/evaluate")
def api_force_evaluate():
    logger.info("Manual evaluation triggered.")
    learn.evaluate_predictions()
    return {"status": "Evaluation batch completed."}

@router.post("/feedback/{prediction_id}")
def api_submit_feedback(prediction_id: int, req: FeedbackRequest):
    conn = data_store._get_conn()
    try:
        row = conn.execute("SELECT * FROM scar_predictions WHERE id = ?", (prediction_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prediction not found")
            
        symbol = row["token_symbol"]
        old_status = row["status"]
        
        conn.execute("""
            UPDATE scar_predictions 
            SET status = ?, result_date = ?
            WHERE id = ?
        """, (req.result, datetime.now(timezone.utc).isoformat(), prediction_id))
        
        # If transitioning to hit, update accuracy and template manually if needed
        # For simplicity in this endpoint, we just update the status and recalculate accuracy
        learn._update_accuracy(conn, symbol, req.result, 0.0) # ROI 0 for manual override
        conn.commit()
        
        return {"status": "ok", "prediction_id": prediction_id, "new_result": req.result}
    finally:
        conn.close()

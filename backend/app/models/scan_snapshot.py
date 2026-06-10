import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, JSON, Boolean
from app.models.job import Base


class ScanSnapshot(Base):
    """
    Captures the state of each recommended stock at the moment of scan,
    then tracks its end-of-day performance to audit scoring accuracy.
    """
    __tablename__ = "scan_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # --- Scan Context ---
    scan_date = Column(String, index=True, nullable=False)       # "2026-06-10"
    scan_job_id = Column(String, index=True, nullable=False)     # Links back to the job
    
    # --- Stock Identity ---
    symbol = Column(String, index=True, nullable=False)
    name = Column(String, nullable=True)
    sector = Column(String, nullable=True)
    
    # --- Score at Time of Scan ---
    rank = Column(Integer, nullable=False)                       # 1 = top pick, 2 = second, etc.
    total_score = Column(Float, nullable=False)
    signal = Column(String, nullable=True)                       # BUY_STRONG, BUY, HOLD
    strategy = Column(String, nullable=True)                     # PULLBACK / BREAKOUT
    setup_type = Column(String, nullable=True)
    confidence = Column(String, nullable=True)                   # HIGH, MEDIUM, LOW
    ai_approved = Column(Boolean, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    
    # --- Key Indicators at Scan Time (for forensics) ---
    entry_price = Column(Float, nullable=False)                  # Price when recommended
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    vol_ratio = Column(Float, nullable=True)                     # Today's volume ratio
    delivery_pct = Column(Float, nullable=True)                  # NSE delivery %
    
    # --- Detailed Scoring Breakdown (JSON blob for full forensics) ---
    reasons_json = Column(JSON, nullable=True)                   # Full reasons[] array from scan
    
    # --- End-of-Day Performance (filled later) ---
    eod_price = Column(Float, nullable=True)                     # Closing price
    eod_change_pct = Column(Float, nullable=True)                # % change from entry to EOD
    eod_high = Column(Float, nullable=True)                      # Intraday high
    eod_low = Column(Float, nullable=True)                       # Intraday low
    max_drawdown_pct = Column(Float, nullable=True)              # Worst intraday drop from entry
    
    # --- Audit Classification ---
    performance_tag = Column(String, nullable=True)              # "WINNER", "LOSER", "TRAP", "NEUTRAL"
    is_tracked = Column(Boolean, default=False)                  # True once EOD data has been filled
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

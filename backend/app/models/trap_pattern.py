import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, JSON, Boolean
from app.models.job import Base


class TrapPattern(Base):
    """
    Stores the indicator fingerprint of a stock that was classified as a TRAP.
    Used by the Trap Memory system to detect similar patterns in future scans.
    """
    __tablename__ = "trap_patterns"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # --- Source ---
    source_symbol = Column(String, nullable=False)             # Which stock created this trap
    source_date = Column(String, index=True, nullable=False)   # When it happened
    loss_pct = Column(Float, nullable=False)                   # How bad was the loss
    
    # --- Indicator Fingerprint (ranges that define the trap) ---
    roc_5d_min = Column(Float, nullable=True)                  # 5-day ROC range
    roc_5d_max = Column(Float, nullable=True)
    vol_ratio_min = Column(Float, nullable=True)               # Volume spike range
    vol_ratio_max = Column(Float, nullable=True)
    ema10_dist_min = Column(Float, nullable=True)              # EMA10 extension range
    ema10_dist_max = Column(Float, nullable=True)
    delivery_pct_min = Column(Float, nullable=True)            # Delivery % range
    delivery_pct_max = Column(Float, nullable=True)
    adx_min = Column(Float, nullable=True)                     # ADX range
    adx_max = Column(Float, nullable=True)
    
    # --- Pattern Classification ---
    trap_type = Column(String, nullable=False)                 # "CLIMAX_VOLUME", "OVEREXTENSION", "LOW_DELIVERY", "UNKNOWN"
    match_count = Column(Integer, default=0)                   # How many future stocks matched this pattern
    confidence = Column(Float, default=1.0)                    # Grows each time the pattern repeats
    
    # --- Full indicator snapshot for AI context ---
    indicators_json = Column(JSON, nullable=True)
    
    is_active = Column(Boolean, default=True)                  # Can be disabled if pattern is stale
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

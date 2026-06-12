import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, Boolean, JSON
from app.models.job import Base

class SwingTrade(Base):
    __tablename__ = "swing_trades"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String, index=True, nullable=False)
    strategy = Column(String, nullable=False) # PULLBACK / BREAKOUT
    setup_type = Column(String, nullable=True) # e.g. "EMA 20 Pullback"
    
    entry = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    initial_stop_loss = Column(Float, nullable=False)
    target = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    
    status = Column(String, default="OPEN") # OPEN, CLOSED
    partial_exit_done = Column(Boolean, default=False)
    
    entry_date = Column(DateTime, default=datetime.utcnow)
    exit_price = Column(Float, nullable=True)
    exit_date = Column(DateTime, nullable=True)
    exit_reason = Column(String, nullable=True)
    
    r_multiple = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    pnl_amount = Column(Float, nullable=True)
    pnl_percentage = Column(Float, nullable=True)
    
    sector = Column(String, nullable=True)
    confidence = Column(String, nullable=True) # HIGH, MEDIUM, LOW
    initial_score = Column(Float, nullable=True)
    current_score = Column(Float, nullable=True)
    scan_data = Column(JSON, nullable=True)
    initial_scan_data = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

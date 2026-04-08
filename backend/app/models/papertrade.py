
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.models.job import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    balance = Column(Float, default=1000000.0) # Initial 10 Lakhs dummy money
    total_pnl = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String, index=True)
    qty = Column(Integer)
    buy_price = Column(Float)
    buy_time = Column(DateTime, default=datetime.utcnow)
    sell_price = Column(Float, nullable=True)
    sell_time = Column(DateTime, nullable=True)
    status = Column(String, default="OPEN") # OPEN, CLOSED
    target = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    score_at_buy = Column(Float, nullable=True)
    order_type = Column(String, default="MARKET") # MARKET, LIMIT
    product_type = Column(String, default="MIS") # MIS, CNC
    close_reason = Column(String, nullable=True) # SL, TARGET, EOD, MANUAL
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

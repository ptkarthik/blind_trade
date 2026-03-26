from sqlalchemy import Column, String
from app.models.job import Base

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(String)

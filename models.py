from datetime import datetime

from sqlalchemy import Column, String, TIMESTAMP, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UrlsDB(Base):
    __tablename__ = "urls_db"

    short = Column(String, primary_key=True, index=True)
    original = Column(String, nullable=False)
    registered_at = Column(TIMESTAMP(timezone=True), default=datetime.now())
    get_num = Column(Integer, default=0)
    last_time = Column(TIMESTAMP(timezone=True))
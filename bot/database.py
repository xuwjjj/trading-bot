from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

Base = declarative_base()


class Trade(Base):
	__tablename__ = "trades"

	id = Column(Integer, primary_key=True)
	symbol = Column(String, nullable=False)
	market_type = Column(String, nullable=False)
	side = Column(String, nullable=False)
	entry_price = Column(Float, nullable=False)
	exit_price = Column(Float)
	take_profit = Column(Float)
	stop_loss = Column(Float)
	position_size = Column(Float, nullable=False)
	status = Column(String, default="open")
	pnl = Column(Float)
	entry_time = Column(DateTime, default=datetime.utcnow)
	exit_time = Column(DateTime)
	reason = Column(String)
	analysis_report = Column(JSON)
	is_paper = Column(Boolean, default=True)


class Settings(Base):
	__tablename__ = "settings"

	id = Column(Integer, primary_key=True)
	key = Column(String, unique=True, nullable=False)
	value = Column(String, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Watchlist(Base):
	__tablename__ = "watchlist"

	id = Column(Integer, primary_key=True)
	symbol = Column(String, unique=True, nullable=False)
	market_type = Column(String, nullable=False)
	added_at = Column(DateTime, default=datetime.utcnow)


connect_args = (
	{"check_same_thread": False}
	if settings.database_url.startswith("sqlite")
	else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def get_db():
	return SessionLocal()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
	pass

# Create engine with better error handling
try:
	engine = create_engine(
		settings.database_url, 
		pool_pre_ping=True, 
		pool_recycle=3600,
		pool_timeout=10,
		connect_args={"connect_timeout": 10}
	)
	SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
	logger.info("Database engine created successfully")
except Exception as e:
	logger.error(f"Failed to create database engine: {e}")
	engine = None
	SessionLocal = None


def get_db():
	from sqlalchemy.orm import Session
	if SessionLocal is None:
		raise Exception("Database not available. Please check your database connection.")
	
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

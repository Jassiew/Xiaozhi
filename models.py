from sqlalchemy import Column, Integer, String, Float, DateTime, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session as _Session
from datetime import datetime, timezone
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(engine, class_=_Session, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(64), unique=True, nullable=False)
    name = Column(String(128), default="")
    bind_code = Column(String(8), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class LearningSession(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(64), nullable=False, index=True)
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime, nullable=True)
    status = Column(String(16), default="active")  # active / ended

class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    fatigue_level = Column(Float, default=0.0)
    distraction_level = Column(Float, default=0.0)
    gaze_direction = Column(String(16), default="")
    action_state = Column(String(16), default="")
    difficulty_indicator = Column(Float, default=0.0)
    learning_state = Column(String(32), default="")
    raw_frame_path = Column(String(256), default="")
    person_present = Column(Integer, default=1)

async def init_db():
    Base.metadata.create_all(engine)

import uuid
from src.backend.database import Base 
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Date, func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

class Users(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True)
    username = Column(String(255), unique=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    hashed_password = Column(String(255))
    current_thread_id = Column(String(255), ForeignKey("threads.thread_id"), nullable=True)
    threads_info = Column(JSONB, nullable=True)
    embedded_docs = Column(ARRAY(String(255)), nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(String(50), default="user")
    created_on = Column(Date, default=func.current_date())
    last_active = Column(DateTime, default=func.now(), onupdate=func.now())



class Threads(Base):
    __tablename__ = "threads"
    
    thread_id = Column(String(255), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(30), default="idle", nullable=False)    # 'idle' | 'running' | 'awaiting_input' | 'fallback' | 'completed'
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_on = Column(Date, default=func.current_date())
    last_used = Column(DateTime, default=func.now(), onupdate=func.now())



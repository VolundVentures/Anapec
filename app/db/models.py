from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    language = Column(String(10), default="fr")
    profile_data = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    messages = Column(JSON, default=list)
    current_task = Column(String(50), nullable=True)
    collected_data = Column(JSON, default=dict)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class GeneratedCV(Base):
    __tablename__ = "generated_cvs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cv_data = Column(JSON, nullable=False)
    enhanced_data = Column(JSON, nullable=True)
    target_job = Column(Text, nullable=True)
    pdf_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class JobListing(Base):
    __tablename__ = "job_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    city = Column(String(100), nullable=False)
    sector = Column(String(100), nullable=False)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    contract_type = Column(String(50), nullable=True)
    experience_level = Column(String(50), nullable=True)
    posted_date = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)

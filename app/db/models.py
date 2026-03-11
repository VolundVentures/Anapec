from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
from sqlalchemy.sql import func
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    language = Column(String(10), default="fr")
    communication_pref = Column(String(10), default="voice")  # "voice" or "text"
    profile_data = Column(JSON, default=dict)

    # CIN (Moroccan National ID) data
    cin_number = Column(String(20), nullable=True)
    cin_data = Column(JSON, nullable=True)  # full OCR output
    full_name_arabic = Column(String(255), nullable=True)
    full_name_latin = Column(String(255), nullable=True)
    date_of_birth = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    gender = Column(String(10), nullable=True)

    # Profile photo
    photo_b64 = Column(Text, nullable=True)

    # Structured profile data
    education = Column(JSON, default=list)
    experience = Column(JSON, default=list)
    extracurricular = Column(JSON, default=list)
    languages_spoken = Column(JSON, default=list)
    driving_license = Column(String(50), nullable=True)
    certifications = Column(JSON, default=list)

    # Industry
    industry_category = Column(String(100), nullable=True)
    industry_details = Column(JSON, default=dict)

    # Onboarding
    onboarding_complete = Column(Boolean, default=False)
    onboarding_step = Column(String(50), nullable=True)
    profile_completeness = Column(Integer, default=0)

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


class OnboardingState(Base):
    __tablename__ = "onboarding_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    step = Column(String(50), nullable=False)
    step_data = Column(JSON, default=dict)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BilanSession(Base):
    __tablename__ = "bilan_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="in_progress")  # in_progress, completed, abandoned
    current_phase = Column(String(50), nullable=True)
    phase_data = Column(JSON, default=dict)
    responses = Column(JSON, default=list)
    scores = Column(JSON, default=dict)
    report_filename = Column(String(255), nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)


class MessageBuffer(Base):
    __tablename__ = "message_buffer"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone_number = Column(String(20), nullable=False)
    message_sid = Column(String(100), nullable=True)
    body = Column(Text, default="")
    media_urls = Column(JSON, default=list)
    media_types = Column(JSON, default=list)
    received_at = Column(DateTime, server_default=func.now())
    processed = Column(Boolean, default=False)


class GeneratedCV(Base):
    __tablename__ = "generated_cvs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cv_data = Column(JSON, nullable=False)
    enhanced_data = Column(JSON, nullable=True)
    target_job = Column(Text, nullable=True)
    template_used = Column(String(100), nullable=True)
    pdf_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class BilanReport(Base):
    __tablename__ = "bilan_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bilan_session_id = Column(Integer, ForeignKey("bilan_sessions.id"), nullable=False)
    report_data = Column(JSON, nullable=True)
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

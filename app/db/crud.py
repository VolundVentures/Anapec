from sqlalchemy.orm import Session
from app.db.models import User, Conversation, GeneratedCV, JobListing
import json


# --- Users ---

def get_or_create_user(db: Session, phone_number: str) -> User:
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if not user:
        user = User(phone_number=phone_number)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def update_user(db: Session, user: User, **kwargs) -> User:
    for key, value in kwargs.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


# --- Conversations ---

def get_conversation(db: Session, user_id: int) -> Conversation:
    conv = db.query(Conversation).filter(Conversation.user_id == user_id).first()
    if not conv:
        conv = Conversation(user_id=user_id, messages=[], collected_data={})
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def update_conversation(db: Session, conv: Conversation, **kwargs) -> Conversation:
    for key, value in kwargs.items():
        setattr(conv, key, value)
    db.commit()
    db.refresh(conv)
    return conv


def add_message(db: Session, conv: Conversation, role: str, content: str):
    messages = list(conv.messages or [])
    messages.append({"role": role, "content": content})
    # Keep last 30 messages
    if len(messages) > 30:
        messages = messages[-30:]
    conv.messages = messages
    db.commit()
    db.refresh(conv)


def reset_conversation(db: Session, conv: Conversation):
    conv.current_task = None
    conv.collected_data = {}
    conv.messages = []
    db.commit()


# --- Generated CVs ---

def save_generated_cv(db: Session, user_id: int, cv_data: dict, enhanced_data: dict = None,
                      target_job: str = None, pdf_filename: str = None) -> GeneratedCV:
    cv = GeneratedCV(
        user_id=user_id,
        cv_data=cv_data,
        enhanced_data=enhanced_data,
        target_job=target_job,
        pdf_filename=pdf_filename,
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return cv


# --- Job Listings ---

def search_jobs(db: Session, city: str = None, sector: str = None, limit: int = 10) -> list[JobListing]:
    query = db.query(JobListing).filter(JobListing.is_active == True)
    if city:
        query = query.filter(JobListing.city.ilike(f"%{city}%"))
    if sector:
        query = query.filter(JobListing.sector.ilike(f"%{sector}%"))
    return query.limit(limit).all()


def get_job_by_id(db: Session, job_id: int) -> JobListing:
    return db.query(JobListing).filter(JobListing.id == job_id).first()


def bulk_insert_jobs(db: Session, jobs: list[dict]):
    for job_data in jobs:
        job = JobListing(**job_data)
        db.add(job)
    db.commit()

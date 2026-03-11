from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.db.models import (
    User, Conversation, GeneratedCV, JobListing,
    OnboardingState, BilanSession, MessageBuffer, BilanReport,
)


# --- Users ---

def get_or_create_user(db: Session, phone_number: str) -> User:
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if not user:
        user = User(phone_number=phone_number)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_user_by_phone(db: Session, phone_number: str) -> User | None:
    return db.query(User).filter(User.phone_number == phone_number).first()


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
    if len(messages) > 50:
        messages = messages[-50:]
    conv.messages = messages
    db.commit()
    db.refresh(conv)


def reset_conversation(db: Session, conv: Conversation):
    conv.current_task = None
    conv.collected_data = {}
    conv.messages = []
    db.commit()


# --- Onboarding State ---

def get_onboarding_state(db: Session, user_id: int) -> OnboardingState | None:
    return db.query(OnboardingState).filter(
        OnboardingState.user_id == user_id
    ).order_by(OnboardingState.updated_at.desc()).first()


def create_onboarding_state(db: Session, user_id: int, step: str) -> OnboardingState:
    state = OnboardingState(user_id=user_id, step=step, step_data={}, attempts=0)
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def update_onboarding_state(db: Session, state: OnboardingState, **kwargs) -> OnboardingState:
    for key, value in kwargs.items():
        setattr(state, key, value)
    db.commit()
    db.refresh(state)
    return state


def set_onboarding_step(db: Session, user_id: int, step: str, step_data: dict = None) -> OnboardingState:
    state = get_onboarding_state(db, user_id)
    if state:
        state.step = step
        state.step_data = step_data or {}
        state.attempts = 0
        db.commit()
        db.refresh(state)
    else:
        state = create_onboarding_state(db, user_id, step)
        if step_data:
            state.step_data = step_data
            db.commit()
            db.refresh(state)
    return state


# --- Bilan Sessions ---

def get_active_bilan(db: Session, user_id: int) -> BilanSession | None:
    return db.query(BilanSession).filter(
        BilanSession.user_id == user_id,
        BilanSession.status == "in_progress",
    ).first()


def create_bilan_session(db: Session, user_id: int) -> BilanSession:
    session = BilanSession(
        user_id=user_id,
        status="in_progress",
        current_phase="introduction",
        phase_data={},
        responses=[],
        scores={},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def update_bilan_session(db: Session, session: BilanSession, **kwargs) -> BilanSession:
    for key, value in kwargs.items():
        setattr(session, key, value)
    db.commit()
    db.refresh(session)
    return session


def complete_bilan_session(db: Session, session: BilanSession, report_filename: str = None):
    session.status = "completed"
    session.completed_at = func.now()
    if report_filename:
        session.report_filename = report_filename
    db.commit()
    db.refresh(session)


# --- Bilan Reports ---

def save_bilan_report(db: Session, user_id: int, bilan_session_id: int,
                      report_data: dict, pdf_filename: str = None) -> BilanReport:
    report = BilanReport(
        user_id=user_id,
        bilan_session_id=bilan_session_id,
        report_data=report_data,
        pdf_filename=pdf_filename,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


# --- Message Buffer ---

def buffer_message(db: Session, user_id: int, phone_number: str,
                   message_sid: str, body: str,
                   media_urls: list = None, media_types: list = None) -> MessageBuffer:
    msg = MessageBuffer(
        user_id=user_id,
        phone_number=phone_number,
        message_sid=message_sid,
        body=body,
        media_urls=media_urls or [],
        media_types=media_types or [],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_pending_messages(db: Session, user_id: int) -> list[MessageBuffer]:
    return db.query(MessageBuffer).filter(
        MessageBuffer.user_id == user_id,
        MessageBuffer.processed == False,
    ).order_by(MessageBuffer.received_at.asc()).all()


def mark_messages_processed(db: Session, messages: list[MessageBuffer]):
    for msg in messages:
        msg.processed = True
    db.commit()


# --- Generated CVs ---

def save_generated_cv(db: Session, user_id: int, cv_data: dict, enhanced_data: dict = None,
                      target_job: str = None, pdf_filename: str = None,
                      template_used: str = None) -> GeneratedCV:
    cv = GeneratedCV(
        user_id=user_id,
        cv_data=cv_data,
        enhanced_data=enhanced_data,
        target_job=target_job,
        pdf_filename=pdf_filename,
        template_used=template_used,
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

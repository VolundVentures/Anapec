from pydantic import BaseModel
from typing import Optional


class Experience(BaseModel):
    title: str = ""
    company: str = ""
    period: str = ""
    descriptions: list[str] = []


class Education(BaseModel):
    degree: str = ""
    institution: str = ""
    year: str = ""


class LanguageSkill(BaseModel):
    language: str = ""
    level: str = ""


class CVData(BaseModel):
    full_name: str = ""
    phone: Optional[str] = None
    email: Optional[str] = None
    city: str = ""
    desired_position: str = ""
    professional_summary: str = ""
    experience: list[Experience] = []
    education: list[Education] = []
    technical_skills: list[str] = []
    soft_skills: list[str] = []
    languages: list[LanguageSkill] = []
    interests: list[str] = []

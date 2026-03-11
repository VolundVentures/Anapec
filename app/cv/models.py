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


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str = ""


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = []
    url: str = ""


class Achievement(BaseModel):
    title: str = ""
    description: str = ""
    metric: str = ""


class Extracurricular(BaseModel):
    activity: str = ""
    role: str = ""
    description: str = ""


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
    driving_license: Optional[str] = None
    extracurricular: list[Extracurricular] = []
    certifications: list[Certification] = []
    projects: list[Project] = []
    tools_equipment: list[str] = []
    achievements: list[Achievement] = []
    industry_category: str = ""

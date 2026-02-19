from pydantic import BaseModel
from typing import Optional


class JobMatch(BaseModel):
    job_id: int
    title: str
    company: str
    city: str
    sector: str
    salary_range: str = ""
    contract_type: str = ""
    match_reason: str = ""

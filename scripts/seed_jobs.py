"""Seed the job listings database from sample_listings.json."""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import init_db, SessionLocal
from app.db.models import JobListing


def seed_jobs():
    init_db()
    db = SessionLocal()

    # Check if already seeded
    existing = db.query(JobListing).count()
    if existing > 0:
        print(f"Database already has {existing} job listings. Skipping seed.")
        db.close()
        return

    # Load sample data
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "jobs", "sample_listings.json"
    )

    with open(data_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    for job_data in jobs:
        job = JobListing(**job_data)
        db.add(job)

    db.commit()
    print(f"Seeded {len(jobs)} job listings successfully.")
    db.close()


if __name__ == "__main__":
    seed_jobs()

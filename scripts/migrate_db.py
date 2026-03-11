"""Database migration script — adds new tables and columns for v2.0."""

import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "anapec.db")


def migrate():
    if not os.path.exists(DB_PATH):
        print("No database found. Run the app first to create it via SQLAlchemy.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── New columns on users table ──
    user_columns = {
        "communication_pref": "VARCHAR(10) DEFAULT 'voice'",
        "cin_number": "VARCHAR(20)",
        "cin_data": "JSON",
        "full_name_arabic": "VARCHAR(255)",
        "full_name_latin": "VARCHAR(255)",
        "date_of_birth": "VARCHAR(20)",
        "city": "VARCHAR(100)",
        "address": "TEXT",
        "gender": "VARCHAR(10)",
        "photo_b64": "TEXT",
        "education": "JSON DEFAULT '[]'",
        "experience": "JSON DEFAULT '[]'",
        "extracurricular": "JSON DEFAULT '[]'",
        "languages_spoken": "JSON DEFAULT '[]'",
        "driving_license": "VARCHAR(50)",
        "certifications": "JSON DEFAULT '[]'",
        "industry_category": "VARCHAR(100)",
        "industry_details": "JSON DEFAULT '{}'",
        "onboarding_complete": "BOOLEAN DEFAULT 0",
        "onboarding_step": "VARCHAR(50)",
        "profile_completeness": "INTEGER DEFAULT 0",
    }

    for col, col_type in user_columns.items():
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            print(f"  Added users.{col}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # ── New columns on generated_cvs ──
    try:
        cursor.execute("ALTER TABLE generated_cvs ADD COLUMN template_used VARCHAR(100)")
        print("  Added generated_cvs.template_used")
    except sqlite3.OperationalError:
        pass

    # ── New tables ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            step VARCHAR(50) NOT NULL,
            step_data JSON DEFAULT '{}',
            attempts INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  Created/verified onboarding_states table")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bilan_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR(20) DEFAULT 'in_progress',
            current_phase VARCHAR(50),
            phase_data JSON DEFAULT '{}',
            responses JSON DEFAULT '[]',
            scores JSON DEFAULT '{}',
            report_filename VARCHAR(255),
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)
    print("  Created/verified bilan_sessions table")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_buffer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            phone_number VARCHAR(20) NOT NULL,
            message_sid VARCHAR(100),
            body TEXT DEFAULT '',
            media_urls JSON DEFAULT '[]',
            media_types JSON DEFAULT '[]',
            received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed BOOLEAN DEFAULT 0
        )
    """)
    print("  Created/verified message_buffer table")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bilan_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            bilan_session_id INTEGER NOT NULL REFERENCES bilan_sessions(id),
            report_data JSON,
            pdf_filename VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  Created/verified bilan_reports table")

    conn.commit()
    conn.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    print(f"Migrating database: {DB_PATH}")
    migrate()

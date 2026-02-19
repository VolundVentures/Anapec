"""One-command demo setup: seeds DB, loads knowledge base, validates config."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def check_env():
    """Validate required environment variables."""
    print("\n=== Checking Environment ===")
    required = {
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
        "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN", ""),
    }

    all_ok = True
    for key, value in required.items():
        if value and len(value) > 5:
            print(f"  [OK] {key} is set")
        else:
            print(f"  [!!] {key} is MISSING — set it in .env file")
            all_ok = False

    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    print(f"  [..] BASE_URL = {base_url}")
    if "localhost" in base_url:
        print("       (Remember to update BASE_URL with your ngrok URL)")

    return all_ok


def seed_database():
    """Seed job listings into SQLite."""
    print("\n=== Seeding Job Listings ===")
    from scripts.seed_jobs import seed_jobs
    seed_jobs()


def seed_knowledge():
    """Seed knowledge base into ChromaDB."""
    print("\n=== Seeding Knowledge Base ===")
    from scripts.seed_knowledge_base import seed_kb
    seed_kb()


def create_dirs():
    """Create necessary directories."""
    print("\n=== Creating Directories ===")
    dirs = ["generated_cvs", "chroma_data"]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in dirs:
        path = os.path.join(root, d)
        os.makedirs(path, exist_ok=True)
        print(f"  [OK] {d}/")


def main():
    print("=" * 50)
    print("  ANAPEC AI Agent — Demo Setup")
    print("=" * 50)

    create_dirs()
    env_ok = check_env()
    seed_database()

    # Knowledge base seeding requires sentence-transformers
    try:
        seed_knowledge()
    except Exception as e:
        print(f"  [!!] Knowledge base seeding failed: {e}")
        print("       (Install sentence-transformers: pip install sentence-transformers)")

    print("\n" + "=" * 50)
    print("  Setup Complete!")
    print("=" * 50)

    if env_ok:
        print("\nNext steps:")
        print("  1. Start the server:  uvicorn app.main:app --reload --port 8000")
        print("  2. Start ngrok:       ngrok http 8000")
        print("  3. Update BASE_URL in .env with ngrok URL")
        print("  4. Set Twilio webhook: https://<ngrok-id>.ngrok-free.app/webhook")
        print("  5. Join Twilio sandbox from WhatsApp")
        print('  6. Send: "Salam, bghit ndir CV"')
    else:
        print("\n[!!] Fix missing environment variables in .env before starting")
        print("     Copy .env.example to .env and fill in your API keys")


if __name__ == "__main__":
    main()

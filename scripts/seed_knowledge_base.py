"""Seed the ChromaDB knowledge base from markdown files."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.knowledge_base import init_knowledge_base


def seed_kb():
    docs_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "knowledge_base"
    )
    print(f"Loading knowledge base from: {docs_dir}")
    init_knowledge_base(docs_dir)
    print("Knowledge base seeded successfully.")


if __name__ == "__main__":
    seed_kb()

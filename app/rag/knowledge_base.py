"""ChromaDB-based knowledge base for ANAPEC documentation."""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Global knowledge base instance
_knowledge_base = None


class KnowledgeBase:
    def __init__(self, persist_dir: str = "./chroma_data"):
        try:
            import chromadb
            self.client = chromadb.PersistentClient(path=persist_dir)
            self.collection = self.client.get_or_create_collection(
                name="anapec_knowledge",
                metadata={"hnsw:space": "cosine"}
            )
            self._embedder = None
            logger.info(f"ChromaDB initialized with {self.collection.count()} documents")
        except Exception as e:
            logger.error(f"ChromaDB initialization failed: {e}")
            self.client = None
            self.collection = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:
                logger.error(f"SentenceTransformer init failed: {e}")
        return self._embedder

    def load_documents(self, docs_dir: str):
        """Load markdown files, chunk, embed, and store in ChromaDB."""
        if not self.collection:
            logger.error("ChromaDB not initialized")
            return

        docs_path = Path(docs_dir)
        if not docs_path.exists():
            logger.error(f"Docs directory not found: {docs_dir}")
            return

        all_chunks = []
        all_ids = []
        all_metadatas = []

        for md_file in docs_path.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            chunks = self._chunk_text(text, chunk_size=500, overlap=100)

            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_ids.append(f"{md_file.stem}_{i}")
                all_metadatas.append({"source": md_file.name, "chunk_index": i})

        if not all_chunks:
            logger.warning("No documents found to load")
            return

        # Embed all chunks
        if self.embedder:
            embeddings = self.embedder.encode(all_chunks).tolist()
            self.collection.upsert(
                documents=all_chunks,
                embeddings=embeddings,
                ids=all_ids,
                metadatas=all_metadatas,
            )
        else:
            # Fallback: store without embeddings (ChromaDB will use default)
            self.collection.upsert(
                documents=all_chunks,
                ids=all_ids,
                metadatas=all_metadatas,
            )

        logger.info(f"Loaded {len(all_chunks)} chunks from {len(list(docs_path.glob('*.md')))} files")

    def query(self, question: str, n_results: int = 5) -> list[str]:
        """Retrieve relevant chunks for a question."""
        if not self.collection or self.collection.count() == 0:
            return []

        try:
            if self.embedder:
                query_embedding = self.embedder.encode([question]).tolist()
                results = self.collection.query(
                    query_embeddings=query_embedding,
                    n_results=min(n_results, self.collection.count()),
                    include=["documents"],
                )
            else:
                results = self.collection.query(
                    query_texts=[question],
                    n_results=min(n_results, self.collection.count()),
                    include=["documents"],
                )

            return results["documents"][0] if results["documents"] else []

        except Exception as e:
            logger.error(f"Knowledge base query failed: {e}")
            return []

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
        """Split text into overlapping chunks by paragraph/section."""
        # Split by double newline (paragraphs) or markdown headers
        sections = []
        current_section = ""

        for line in text.split("\n"):
            if line.startswith("## ") and current_section:
                sections.append(current_section.strip())
                current_section = line + "\n"
            elif line.startswith("# ") and current_section:
                sections.append(current_section.strip())
                current_section = line + "\n"
            else:
                current_section += line + "\n"

        if current_section.strip():
            sections.append(current_section.strip())

        # Further split large sections
        chunks = []
        for section in sections:
            words = section.split()
            if len(words) <= chunk_size:
                chunks.append(section)
            else:
                for i in range(0, len(words), chunk_size - overlap):
                    chunk = " ".join(words[i:i + chunk_size])
                    if chunk.strip():
                        chunks.append(chunk)

        return [c for c in chunks if len(c.strip()) > 20]


def get_knowledge_base() -> KnowledgeBase:
    """Get or create the global knowledge base instance."""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase()
    return _knowledge_base


def init_knowledge_base(docs_dir: str):
    """Initialize and load the knowledge base."""
    kb = get_knowledge_base()
    if kb.collection and kb.collection.count() == 0:
        logger.info("Loading knowledge base documents...")
        kb.load_documents(docs_dir)
    else:
        logger.info(f"Knowledge base already loaded ({kb.collection.count() if kb.collection else 0} chunks)")

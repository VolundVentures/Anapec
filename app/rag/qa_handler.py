"""RAG-based Q&A handler for ANAPEC service questions."""

import logging
from app.agent.claude_client import chat_sync as chat
from app.agent.prompts import RAG_QA_SYSTEM
from app.rag.knowledge_base import get_knowledge_base

logger = logging.getLogger(__name__)


def answer_anapec_question(question: str, language: str = "fr") -> str:
    """Answer an ANAPEC-related question using RAG."""
    try:
        # Retrieve relevant context
        kb = get_knowledge_base()
        chunks = kb.query(question, n_results=4)

        if not chunks:
            return _fallback_answer(question, language)

        context = "\n---\n".join(chunks)

        response = chat(
            system=RAG_QA_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}"
            }],
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            temperature=0.3,
        )

        answer = response.strip()

        # Add a helpful footer
        answer += "\n\n💡 Pour plus d'informations, appelez le numéro vert gratuit: *0800 00 77 00*"
        return answer

    except Exception as e:
        logger.error(f"Q&A handler error: {e}")
        return _fallback_answer(question, language)


def _fallback_answer(question: str, language: str) -> str:
    """Fallback when RAG isn't available."""
    try:
        response = chat(
            system=("You are an ANAPEC customer service assistant. Answer based on your general knowledge "
                    "of ANAPEC Morocco. Be helpful and respond in the user's language. "
                    "If unsure, suggest visiting www.anapec.org or the nearest agency."),
            messages=[{"role": "user", "content": question}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=512,
            temperature=0.3,
        )
        return response.strip() + "\n\n📞 Numéro vert ANAPEC: *0800 00 77 00*"
    except Exception:
        return ("Désolé, je ne peux pas répondre à cette question pour le moment.\n\n"
                "📞 Appelez le numéro vert gratuit: *0800 00 77 00*\n"
                "🌐 Visitez: www.anapec.org")

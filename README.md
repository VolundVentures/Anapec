# Anapec AI Agent

An autonomous WhatsApp AI agent for Moroccan job seekers, powered by Claude.

## What It Does

**3 core capabilities — all via WhatsApp:**

1. **CV Generation** — User sends "bghit ndir CV" and within minutes has a professional PDF CV. The agent asks adaptive questions, enhances content with Claude Opus, and generates a beautiful two-column PDF. Users can also upload a photo of an existing CV for instant improvement.

2. **Job Search & Matching** — "bghit nkhdem f Casa f logistique" returns ranked job listings with personalized match explanations. The agent can then tailor the user's CV for a specific position.

3. **ANAPEC Q&A** — "Kifach ndir inscription?" gets step-by-step guidance about ANAPEC services, agencies, programs (IDMAJ, TAHFIZ, TAEHIL), all powered by RAG over ANAPEC documentation.

**The agent is autonomous, not a chatbot** — it takes initiative, chains actions, and anticipates needs. It handles Darija (Moroccan Arabic), French, and Arabic natively.

## Tech Stack

- **Backend:** Python / FastAPI
- **AI:** Anthropic Claude (Opus for CV enhancement, Sonnet for routing)
- **Vision:** Claude Vision API for CV photo extraction
- **PDF:** WeasyPrint + Jinja2 templates
- **RAG:** ChromaDB + sentence-transformers
- **Database:** SQLite / SQLAlchemy
- **WhatsApp:** Twilio WhatsApp Sandbox

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys:
# - ANTHROPIC_API_KEY
# - TWILIO_ACCOUNT_SID
# - TWILIO_AUTH_TOKEN
```

### 3. Run Demo Setup

```bash
python scripts/demo_setup.py
```

This seeds the job database and knowledge base.

### 4. Start the Server

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Expose with ngrok

```bash
ngrok http 8000
```

Update `BASE_URL` in `.env` with your ngrok URL.

### 6. Configure Twilio

1. Go to Twilio Console → Messaging → WhatsApp Sandbox
2. Set webhook URL: `https://<ngrok-id>.ngrok-free.app/webhook` (POST)
3. Join the sandbox from your WhatsApp

### 7. Test

Send these messages from WhatsApp:

- **CV:** "Salam, bghit ndir CV"
- **Jobs:** "bghit nkhdem f Casablanca f logistique"
- **Q&A:** "Kifach ndir inscription f ANAPEC?"
- **Photo CV:** Send a photo of an existing CV

## Project Structure

```
app/
├── api/webhook.py          # Twilio webhook endpoint
├── agent/orchestrator.py   # The brain — autonomous task execution
├── agent/prompts.py        # All Claude system prompts
├── cv/generator.py         # CV data collection
├── cv/enhancer.py          # Claude Opus CV enhancement
├── cv/pdf.py               # PDF generation
├── vision/cv_extractor.py  # Photo → CV data (Vision API)
├── jobs/search.py          # Job search + matching
├── rag/qa_handler.py       # RAG-based Q&A
templates/cv/modern.html    # Beautiful CV PDF template
data/knowledge_base/        # ANAPEC documentation (5 files)
data/jobs/                  # Mock job listings (50+ entries)
```

## Demo Script

**Scene 1 — CV from Scratch (2 min):**
Send: "Salam, bghit ndir CV, ana khddam f logistique f Casa mn 5 snin"
→ Agent asks follow-up questions → Generates PDF → Sends to WhatsApp

**Scene 2 — CV from Photo (1 min):**
Send a photo of an old/handwritten CV
→ Agent extracts info → Enhances → Sends new professional PDF

**Scene 3 — Job Search (1 min):**
Send: "Show me IT jobs in Rabat"
→ Ranked listings with match explanations

**Scene 4 — ANAPEC Info (30 sec):**
Send: "Fin kayn aqrab agence ANAPEC f Casa?"
→ Agency addresses, hours, phone numbers

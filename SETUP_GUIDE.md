# UNIDO IEU Evaluation Intelligence Platform — Setup Guide

## Overview

This is a RAG (Retrieval-Augmented Generation) system that lets you ask natural language questions across 50 UNIDO evaluation reports and get grounded, cited answers.

**Stack:** Streamlit → FastAPI → LlamaIndex → Qdrant Cloud (vector store) → Claude (LLM)

---

## Step 1: Get your API accounts (all free)

### 1a. Qdrant Cloud (vector database)
1. Go to **https://cloud.qdrant.io** → Sign up free
2. Click **Create Cluster** → Choose **Free Forever** tier → Select **EU region**
3. Wait ~2 minutes for the cluster to spin up
4. Go to **API Keys** tab → Click **Create API Key** → Copy the key
5. Note your **Cluster URL** (looks like `https://xyz.eu-central.aws.cloud.qdrant.io:6333`)

### 1b. LangSmith (query tracing + quality monitoring)
1. Go to **https://smith.langchain.com** → Sign up free
2. Go to **Settings** → **API Keys** → **Create API Key** → Copy it
3. Create a new project called `unido-ieu`

### 1c. OpenAI API (for embeddings only)
> This is NOT ChatGPT Plus — it's the developer API (separate account)
1. Go to **https://platform.openai.com** → Sign up
2. Go to **Billing** → Add $5–10 credit (will last months at our usage volume)
3. Go to **API Keys** → **Create new secret key** → Copy it

---

## Step 2: Configure credentials

```bash
cd eio-rag
cp .env.example .env
```

Open `.env` and fill in:
```
ANTHROPIC_API_KEY=      # Your existing Anthropic key
OPENAI_API_KEY=         # OpenAI key from Step 1c
QDRANT_URL=             # Cluster URL from Step 1a (with :6333)
QDRANT_API_KEY=         # API key from Step 1a
LANGSMITH_API_KEY=      # Key from Step 1b
```

---

## Step 3: Install dependencies

```bash
# Backend
cd eio-rag/backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Note: torch (~2GB) takes a few minutes to install — this is for the reranker
```

---

## Step 4: Add your PDFs

1. Place all 50 PDF files in `eio-rag/data/pdfs/`
2. Open `eio-rag/data/metadata.yaml`
3. Add one entry per report — follow the template format
   - `filename` must match exactly (including capitalisation)
   - `thematic_category` must be one of the 11 listed categories
   - `sdgs` are integers (e.g. `[7, 13, 17]`)
   - `dac_criteria` are from: Relevance, Coherence, Effectiveness, Efficiency, Impact, Sustainability

---

## Step 5: Run ingestion (trains the system on your 50 reports)

```bash
cd eio-rag
source backend/venv/bin/activate
python scripts/ingest.py
```

This will:
- Connect to Qdrant and create the collection
- Extract text from each PDF
- Split into ~512-token passages
- Generate embeddings via OpenAI
- Upload everything to Qdrant
- Print a summary at the end

**Expected time:** ~3–5 minutes for 50 reports (~6 seconds per report)
**Expected cost:** ~$0.02 total in OpenAI embedding tokens

---

## Step 6: Run the backend

```bash
cd eio-rag/backend
source venv/bin/activate
python main.py
# → Running at http://localhost:8000
# → API docs at http://localhost:8000/docs
```

---

## Step 7: Run the Streamlit frontend

In a new terminal:
```bash
cd eio-rag/frontend
pip install -r requirements.txt
streamlit run app.py
# → Opens at http://localhost:8501
```

The app will open in your browser. Click **Check connection** in the sidebar to verify everything is working.

---

## Step 8: Share with your team (temporary URL)

```bash
# Install ngrok from https://ngrok.com (free)
ngrok http 8000        # tunnels the backend
```

Then deploy the frontend to **Streamlit Community Cloud**:
1. Push the `eio-rag/frontend/` folder to a GitHub repo
2. Go to **https://share.streamlit.io** → Connect GitHub → Deploy `app.py`
3. In Streamlit Cloud app settings → **Secrets** → paste: `BACKEND_URL = "https://your-ngrok-url.ngrok.io"`

Your team gets a permanent HTTPS URL for the Streamlit app. The backend runs on your laptop via ngrok.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `OPENAI_API_KEY not set` | Check `.env` file is in the `eio-rag/` root (not in `backend/`) |
| Qdrant connection refused | Check `QDRANT_URL` includes `:6333` port |
| PDF not found during ingestion | Check `filename` in metadata.yaml matches exactly |
| Cross-encoder slow on first query | Normal — it loads a 80MB model once then stays in memory |
| Streamlit can't reach backend | Make sure `python main.py` is running and BACKEND_URL is correct |

---

## What gets stored where

- **Qdrant Cloud**: All document vectors + metadata (the "trained" knowledge base)
- **Your laptop**: Source PDFs (not uploaded anywhere), code, .env credentials
- **Streamlit Cloud**: Only the frontend code (no credentials, no PDFs)
- **GitHub**: Only code (`.env` and PDFs are in `.gitignore`)

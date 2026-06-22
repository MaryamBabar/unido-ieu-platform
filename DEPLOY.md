# Deployment Guide — UNIDO IEU Platform

## What you're deploying

```
Team browser → Streamlit Community Cloud → Railway (FastAPI backend) → Qdrant Cloud
```

- **Qdrant Cloud** — already done ✅ (51 reports ingested)
- **Railway** — hosts the FastAPI backend (free $5/month credit)
- **Streamlit Community Cloud** — hosts the frontend (free)

---

## Step 1 — Push to GitHub

1. Go to **github.com** → click **New repository**
2. Name it: `unido-ieu-platform`
3. Set to **Private** (contains your users config)
4. Do NOT initialise with README (you already have files)
5. Click **Create repository**

GitHub will show you commands. Open PowerShell in the project root and run:

```powershell
cd "C:\Users\Maryam\Documents\Claude\Projects\UNIDO AI\eio-rag"
git init
git add .
git commit -m "Initial commit — UNIDO IEU platform"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/unido-ieu-platform.git
git push -u origin main
```

> ⚠️ The `.gitignore` excludes `.env`, PDFs, and `data/users.yaml` — these will NOT be pushed to GitHub. That is correct.

---

## Step 2 — Deploy backend to Railway

1. Go to **railway.app** → Sign up with your GitHub account
2. Click **New Project** → **Deploy from GitHub repo**
3. Select `unido-ieu-platform`
4. Railway will detect it has Python code — click **Add service** → select the repo
5. In the service settings, set **Root Directory** to `backend`
6. Railway will auto-detect the `Procfile` and use: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Add environment variables in Railway:

Go to your service → **Variables** tab → add each one:

| Variable | Value |
|---|---|
| `QDRANT_URL` | your Qdrant cluster URL (from qdrant.io dashboard) |
| `QDRANT_API_KEY` | your Qdrant API key |
| `QDRANT_COLLECTION` | `unido_evaluations` |
| `LANGSMITH_API_KEY` | your LangSmith key (or leave blank) |
| `LANGCHAIN_TRACING_V2` | `false` |

7. Click **Deploy** — first deploy takes ~5 minutes (downloads the 990MB models)
8. Once deployed, Railway gives you a URL like: `https://unido-ieu-platform-production.up.railway.app`
9. Test it: open `https://YOUR-RAILWAY-URL/api/v1/health` in your browser — you should see JSON

> 💡 Railway gives you $5/month free credit. The backend will cost roughly $3–5/month depending on usage.

---

## Step 3 — Deploy frontend to Streamlit Community Cloud

1. Go to **share.streamlit.io** → Sign in with GitHub
2. Click **New app**
3. Select your repo: `unido-ieu-platform`
4. Set **Branch**: `main`
5. Set **Main file path**: `frontend/app.py`
6. Click **Advanced settings** → **Secrets** and paste:

```toml
BACKEND_URL = "https://YOUR-RAILWAY-URL.up.railway.app"
```

(Replace with your actual Railway URL from Step 2)

7. Click **Deploy** — takes ~2 minutes
8. Streamlit gives you a URL like: `https://your-app.streamlit.app`

---

## Step 4 — Create user accounts for your team

Once the app is live, log in as admin (username: `maryam.babar`) and go to the **Admin** tab to create accounts for your 5 team members.

Or run this locally while the backend is running:

```powershell
cd "C:\Users\Maryam\Documents\Claude\Projects\UNIDO AI\eio-rag\backend"
python ../scripts/create_admin.py
```

---

## Step 5 — Share with team

Send your team the Streamlit URL. They log in with the accounts you created.

---

## Keeping it running

- **Railway** keeps the backend running 24/7 (no sleep on paid tier)
- **Streamlit Cloud** is always on
- If you push new code to GitHub, both services redeploy automatically

## If you need to re-ingest PDFs later

Re-ingestion only needs to happen if you add new reports. Run it locally on your laptop — the results go straight to Qdrant Cloud. No need to redeploy anything.


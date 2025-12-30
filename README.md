# Time Police - ClickUp Audit System

## 🚔 Overview
Detects timesheet fraud in ClickUp by analyzing time entries for:
- **0s Signature**: Entries with exactly 0 seconds (manual entry)
- **Short Duration**: Entries under 5 minutes

## 📁 Project Structure
```
time_police/
├── app.py              # FastAPI backend
├── time_audit.py       # CLI script (original)
├── requirements.txt    # Python dependencies
├── Procfile           # Railway deployment
└── frontend/
    └── index.html     # Dashboard UI
```

## 🚀 Quick Start

### Run Backend Locally
```bash
pip install -r requirements.txt
python app.py
```
Backend runs at: http://localhost:8000
API docs at: http://localhost:8000/docs

### Run Frontend Locally
Just open `frontend/index.html` in your browser.

## 🌐 Deployment

### Backend → Railway (or Render)
1. Push to GitHub
2. Go to [railway.app](https://railway.app)
3. New Project → Deploy from GitHub
4. Add environment variables:
   - `CLICKUP_API_KEY` = your API key
   - `CLICKUP_TEAM_ID` = your team ID

### Frontend → Netlify
1. Go to [netlify.com](https://netlify.com)
2. Drag & drop the `frontend` folder
3. Update `apiUrl` in the dashboard to your Railway URL

## ⏰ Scheduled Daily Runs (6 PM)

### Option 1: Railway Cron
Add to `railway.json`:
```json
{
  "deploy": {
    "cronSchedule": "0 18 * * *"
  }
}
```

### Option 2: GitHub Actions
Create `.github/workflows/daily-audit.yml`:
```yaml
name: Daily Audit
on:
  schedule:
    - cron: '0 18 * * *'
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - run: curl https://your-api.railway.app/api/audit
```

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/api/audit?hours=9.5` | GET | Run audit |
| `/api/health` | GET | Connection status |
| `/docs` | GET | Swagger UI |

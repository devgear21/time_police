#!/usr/bin/env python3
"""
Time Police - FastAPI Backend
=============================
REST API for ClickUp Time Entry Auditing
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
import httpx

# =============================================================================
# CONFIGURATION
# =============================================================================
API_KEY = os.getenv("CLICKUP_API_KEY")
TEAM_ID = os.getenv("CLICKUP_TEAM_ID")

if not API_KEY or not TEAM_ID:
    raise ValueError("Missing required environment variables: CLICKUP_API_KEY and CLICKUP_TEAM_ID")

# Fraud detection thresholds
SHORT_TASK_THRESHOLD_MINUTES = 5

# Time range (in hours)
TIME_RANGE_HOURS = 9.5

# ClickUp API Configuration
BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {
    "Authorization": API_KEY,
    "Content-Type": "application/json"
}

# =============================================================================
# FASTAPI APP
# =============================================================================
app = FastAPI(
    title="🚔 Time Police API",
    description="ClickUp Time Entry Fraud Detection System",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your Netlify URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================
class AuditSummary(BaseModel):
    total: int
    fraud: int
    potential: int
    clean: int


class TimeEntry(BaseModel):
    user: str
    email: str
    duration: str
    duration_ms: int
    verdict: str


class TaskGroup(BaseModel):
    task_name: str
    task_id: str
    status: str
    entries: list[TimeEntry]


class AuditResponse(BaseModel):
    success: bool
    timestamp: str
    audit_period: dict
    summary: AuditSummary
    tasks: list[TaskGroup]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def ms_to_datetime(ms_timestamp: Optional[str]) -> Optional[datetime]:
    """Convert milliseconds timestamp string to datetime object."""
    if ms_timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms_timestamp) / 1000)
    except (ValueError, TypeError):
        return None


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime to human-readable string."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def ms_to_duration_str(duration_ms: int) -> str:
    """Convert duration in milliseconds to readable format like '1h 30m 45s'."""
    total_seconds = int(duration_ms) // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    
    return " ".join(parts)


# =============================================================================
# FRAUD DETECTION FUNCTIONS
# =============================================================================
def check_zero_seconds_trap(duration_ms: int) -> bool:
    """CHECK 1: Zero Seconds Trap - manual entry signature."""
    total_seconds = int(duration_ms) // 1000
    seconds = total_seconds % 60
    return seconds == 0 and duration_ms > 0


def check_short_task(duration_ms: int) -> bool:
    """CHECK 2: Short Task Flag - duration < 5 minutes."""
    duration_minutes = duration_ms / 60000
    return duration_minutes < SHORT_TASK_THRESHOLD_MINUTES


def get_verdict(duration_ms: int) -> str:
    """Apply fraud detection checks and return verdict."""
    verdicts = []
    
    if check_zero_seconds_trap(duration_ms):
        verdicts.append("🚨 FRAUD (0s Signature)")
    
    if check_short_task(duration_ms):
        verdicts.append("⚠️ POTENTIAL FRAUD (Short Duration)")
    
    if verdicts:
        return " | ".join(verdicts)
    
    return "✅ CLEAN"


# =============================================================================
# API FUNCTIONS (ASYNC)
# =============================================================================
async def get_all_users(client: httpx.AsyncClient, team_id: str) -> list:
    """Fetch all users in the workspace."""
    url = f"{BASE_URL}/team/{team_id}"
    
    try:
        response = await client.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        members = data.get("team", {}).get("members", [])
        users = []
        for member in members:
            user = member.get("user", {})
            users.append({
                "id": str(user.get("id")),
                "username": user.get("username", "Unknown"),
                "email": user.get("email", "")
            })
        
        return users
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []


async def get_time_entries_for_user(client: httpx.AsyncClient, team_id: str, 
                                     start_date: int, end_date: int, user_id: str) -> list:
    """Fetch time entries for a single user."""
    url = f"{BASE_URL}/team/{team_id}/time_entries"
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "assignee": user_id
    }
    
    try:
        response = await client.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        print(f"Error fetching entries for user {user_id}: {e}")
        return []


async def get_all_time_entries(client: httpx.AsyncClient, team_id: str, 
                                start_date: int, end_date: int, user_ids: list) -> list:
    """Fetch time entries for all users in parallel."""
    import asyncio
    
    tasks = [
        get_time_entries_for_user(client, team_id, start_date, end_date, uid)
        for uid in user_ids
    ]
    
    results = await asyncio.gather(*tasks)
    
    all_entries = []
    for entries in results:
        all_entries.extend(entries)
    
    return all_entries


# =============================================================================
# STATIC FILES - Serve Frontend
# =============================================================================

# Get the directory where app.py is located
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Mount static files (CSS, JS, images if any)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# =============================================================================
# API ENDPOINTS
# =============================================================================
@app.get("/")
async def serve_frontend():
    """Serve the main dashboard page."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"status": "online", "service": "🚔 Time Police API", "message": "Frontend not found. Use /docs for API."}


@app.get("/api/audit", response_model=AuditResponse)
async def run_audit(hours: float = TIME_RANGE_HOURS):
    """
    Run time entry audit for the specified time range.
    
    - **hours**: Number of hours to look back (default: 9.5)
    """
    now = datetime.now()
    start_of_period = now - timedelta(hours=hours)
    
    end_date_ms = int(now.timestamp() * 1000)
    start_date_ms = int(start_of_period.timestamp() * 1000)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Fetch all users
        users = await get_all_users(client, TEAM_ID)
        
        if not users:
            raise HTTPException(status_code=500, detail="Failed to fetch users")
        
        user_ids = [u['id'] for u in users]
        
        # Step 2: Fetch time entries for all users (parallel)
        entries = await get_all_time_entries(client, TEAM_ID, start_date_ms, end_date_ms, user_ids)
    
    # Step 3: Process entries and group by task
    tasks_data = defaultdict(list)
    fraud_count = 0
    potential_count = 0
    clean_count = 0
    
    for entry in entries:
        user = entry.get("user", {})
        user_name = user.get("username", "Unknown User")
        user_email = user.get("email", "")
        
        task = entry.get("task") or {}
        task_name = task.get("name", "No Task") if task else "No Task"
        task_id = task.get("id", "N/A") if task else "N/A"
        
        duration_ms = int(entry.get("duration", 0))
        duration_str = ms_to_duration_str(duration_ms)
        
        verdict = get_verdict(duration_ms)
        
        if "FRAUD" in verdict and "POTENTIAL" not in verdict:
            fraud_count += 1
        elif "POTENTIAL" in verdict:
            potential_count += 1
        else:
            clean_count += 1
        
        task_key = (task_name, task_id)
        tasks_data[task_key].append({
            "user": user_name,
            "email": user_email,
            "duration": duration_str,
            "duration_ms": duration_ms,
            "verdict": verdict
        })
    
    # Step 4: Format response
    def get_task_status(entries):
        has_fraud = any("FRAUD" in e['verdict'] and "POTENTIAL" not in e['verdict'] for e in entries)
        has_potential = any("POTENTIAL" in e['verdict'] for e in entries)
        if has_fraud:
            return "fraud"
        elif has_potential:
            return "potential"
        return "clean"
    
    # Sort tasks: fraud first
    sorted_tasks = sorted(
        tasks_data.items(),
        key=lambda x: (0 if get_task_status(x[1]) == "fraud" else (1 if get_task_status(x[1]) == "potential" else 2))
    )
    
    task_groups = [
        TaskGroup(
            task_name=task_key[0],
            task_id=task_key[1],
            status=get_task_status(entries),
            entries=[TimeEntry(**e) for e in sorted(entries, key=lambda x: (0 if "FRAUD" in x['verdict'] and "POTENTIAL" not in x['verdict'] else (1 if "POTENTIAL" in x['verdict'] else 2)))]
        )
        for task_key, entries in sorted_tasks
    ]
    
    return AuditResponse(
        success=True,
        timestamp=now.isoformat(),
        audit_period={
            "start": format_datetime(start_of_period),
            "end": format_datetime(now),
            "hours": hours
        },
        summary=AuditSummary(
            total=len(entries),
            fraud=fraud_count,
            potential=potential_count,
            clean=clean_count
        ),
        tasks=task_groups
    )


@app.get("/api/health")
async def health_check():
    """API health check with ClickUp connection test."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/team/{TEAM_ID}", headers=HEADERS)
            clickup_status = "connected" if response.status_code == 200 else "error"
        except:
            clickup_status = "disconnected"
    
    return {
        "api": "healthy",
        "clickup": clickup_status,
        "team_id": TEAM_ID,
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# RUN SERVER
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

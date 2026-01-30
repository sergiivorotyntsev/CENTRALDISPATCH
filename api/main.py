"""FastAPI Control Panel for Vehicle Transport Automation.

Run with: uvicorn api.main:app --reload --port 8000

Endpoints:
- /api/settings - Configuration management
- /api/test - Test/Sandbox (upload, preview, dry-run)
- /api/runs - Run history and logs
- /api/health - Health check
"""
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from api.routes import settings, test, runs, health
from api.database import init_db

app = FastAPI(
    title="Vehicle Transport Automation",
    description="Control Panel for Email-to-ClickUp Pipeline",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(test.router, prefix="/api/test", tags=["Test/Sandbox"])
app.include_router(runs.router, prefix="/api/runs", tags=["Runs/History"])

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()


# Serve frontend (simple HTML for now)
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Vehicle Transport Automation</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            h1 { color: #333; }
            .nav { margin: 20px 0; }
            .nav a { display: inline-block; margin: 5px 10px 5px 0; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
            .nav a:hover { background: #0056b3; }
            .status { padding: 10px; background: #d4edda; border-radius: 4px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚗 Vehicle Transport Automation</h1>
            <p>Control Panel for Email-to-ClickUp Pipeline</p>

            <div class="status">
                ✅ API Server Running
            </div>

            <div class="nav">
                <a href="/api/docs">📚 API Documentation</a>
                <a href="/api/health">❤️ Health Check</a>
                <a href="/api/settings/status">⚙️ Settings Status</a>
                <a href="/api/runs/">📊 Run History</a>
            </div>

            <h2>Quick Links</h2>
            <ul>
                <li><strong>Settings:</strong> <code>GET/POST /api/settings/*</code></li>
                <li><strong>Test Upload:</strong> <code>POST /api/test/upload</code></li>
                <li><strong>Preview CD:</strong> <code>POST /api/test/preview-cd</code></li>
                <li><strong>Dry Run:</strong> <code>POST /api/test/dry-run</code></li>
                <li><strong>Run History:</strong> <code>GET /api/runs/</code></li>
            </ul>
        </div>
    </body>
    </html>
    """

"""SIH26261 FastAPI application entry point.

DISCLAIMER: This is a functional prototype for demonstration purposes only.
It is NOT production-ready, NOT security-audited, NOT certified, and does NOT
issue official AICTE approvals or interact with any government systems.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.api.auth import router as auth_router
from app.api.applications import router as apps_router
from app.api.rulebooks import router as rulebooks_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure storage directory exists and schema is initialized."""
    from app.config import get_settings
    from app.database import Base, engine
    import app.models  # noqa: F401
    settings = get_settings()
    os.makedirs(settings.STORAGE_ROOT, exist_ok=True)
    logger.info(f"Storage root: {settings.STORAGE_ROOT}")
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Database schema initialization warning: {e}")
    yield


app = FastAPI(
    title="SIH26261 – AICTE Compliance Verification System",
    description=(
        "AI-assisted application validation, document authentication and AICTE compliance verification. "
        "PROTOTYPE — not a production government system."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:80",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(apps_router)
app.include_router(rulebooks_router)

# Mount frontend static directories
from fastapi import HTTPException
from fastapi.responses import FileResponse
frontend_dir = os.environ.get(
    "FRONTEND_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
)
if os.path.exists(frontend_dir):
    css_dir = os.path.join(frontend_dir, "css")
    js_dir = os.path.join(frontend_dir, "js")
    assets_dir = os.path.join(frontend_dir, "assets")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

@app.get("/health")
@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "service": "SIH26261 AICTE Compliance Verification System",
        "version": "0.1.0",
        "disclaimer": "functional prototype only",
    }


@app.get("/login")
@app.get("/login.html")
def login_page():
    login_path = os.path.join(frontend_dir, "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path)
    raise HTTPException(status_code=404, detail="Login page not found")


@app.get("/")
@app.get("/index.html")
def root():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "service": "SIH26261 AICTE Compliance Verification",
        "version": "0.1.0",
        "status": "prototype",
        "docs": "/docs",
    }


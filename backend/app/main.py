from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.excel_service import ensure_storage_dirs
from app.routers import auth, locks, sessions, templates


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = Path(__file__).resolve().parents[2] / "frontend"


@app.on_event("startup")
def startup() -> None:
    ensure_storage_dirs()
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return FileResponse(frontend_dir / "index.html")


app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(sessions.router)
app.include_router(locks.router)

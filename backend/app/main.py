from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes_conversation import router as conversation_router
from app.api.routes_scrape import router as scrape_router
from app.core.config import get_settings
from app.db.database import SessionLocal, init_db
from app.db.models import Project

settings = get_settings()
app = FastAPI(title="AutoSenti API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        if not db.get(Project, 1):
            db.add(Project(id=1, name="Default Project", description="Local workspace project"))
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mock_llm": not settings.real_llm_enabled,
        "real_llm_enabled": settings.real_llm_enabled,
        "model": settings.resolved_model if settings.real_llm_enabled else "mock-llm",
    }


app.include_router(conversation_router)
app.include_router(scrape_router)
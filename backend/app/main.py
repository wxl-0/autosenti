from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes_agent import router as agent_router
from app.api.routes_conversation import router as conversation_router
from app.api.routes_clusters import router as clusters_router
from app.api.routes_evaluation import router as evaluation_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_memory import router as memory_router
from app.api.routes_opportunities import router as opportunities_router
from app.api.routes_prd import router as prd_router
from app.api.routes_upload import router as upload_router
from app.api.routes_scrape import router as scrape_router
from app.core.config import get_settings
from app.db.database import SessionLocal, init_db
from app.db.models import Project

settings = get_settings()
app = FastAPI(title="FeedbackOS Agent API", version="0.1.0")
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


app.include_router(upload_router)
app.include_router(conversation_router)
app.include_router(feedback_router)
app.include_router(agent_router)
app.include_router(clusters_router)
app.include_router(opportunities_router)
app.include_router(prd_router)
app.include_router(memory_router)
app.include_router(evaluation_router)
app.include_router(scrape_router)

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.analysis_graph import run_analysis_workflow
from app.db.database import get_db
from app.db.models import AgentRun

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


class ScrapeRequest(BaseModel):
    target_brand: str
    competitor_brands: list[str]
    max_pages: int = 3
    conversation_id: str = "legacy"


@router.post("")
async def scrape_and_analyze(req: ScrapeRequest, db: Session = Depends(get_db)):
    state = await run_analysis_workflow(
        db,
        target_brand=req.target_brand,
        competitor_brands=req.competitor_brands,
        max_pages=req.max_pages,
        conversation_id=req.conversation_id,
    )
    return {
        "run_id": state.get("run_id"),
        "report_markdown": state.get("report_markdown", ""),
        "final_output": state.get("final_output", ""),
        "interception_suggestions": state.get("interception_suggestions", []),
        "has_interception_opportunity": state.get("has_interception_opportunity", False),
        "dimensions": state.get("dimensions", []),
        "total_review_count": state.get("total_review_count", 0),
    }


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    runs = db.query(AgentRun).filter(
        AgentRun.user_task.like("竞品分析：%")
    ).order_by(AgentRun.id.desc()).limit(20).all()
    return [
        {
            "run_id": r.id,
            "status": r.status,
            "user_task": r.user_task,
            "final_output": r.final_output,
            "report_markdown": r.report_markdown,
            "created_at": str(r.created_at),
        }
        for r in runs
    ]

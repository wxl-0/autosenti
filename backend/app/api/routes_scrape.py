import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.analysis_graph import run_analysis_workflow
from app.db.database import get_db
from app.db.models import AgentRun

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


class ScrapeRequest(BaseModel):
    target_brand: str
    competitor_brands: list[str]
    max_pages: int = 5
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


@router.post("/stream")
async def scrape_and_analyze_stream(req: ScrapeRequest, db: Session = Depends(get_db)):
    queue: asyncio.Queue = asyncio.Queue()

    async def run_pipeline():
        try:
            state = await run_analysis_workflow(
                db,
                target_brand=req.target_brand,
                competitor_brands=req.competitor_brands,
                max_pages=req.max_pages,
                conversation_id=req.conversation_id,
                progress_queue=queue,
            )
            await queue.put({
                "done": True,
                "result": {
                    "run_id": state.get("run_id"),
                    "report_markdown": state.get("report_markdown", ""),
                    "final_output": state.get("final_output", ""),
                    "interception_suggestions": state.get("interception_suggestions", []),
                    "has_interception_opportunity": state.get("has_interception_opportunity", False),
                    "dimensions": state.get("dimensions", []),
                    "total_review_count": state.get("total_review_count", 0),
                },
            })
        except Exception as exc:
            await queue.put({"done": True, "error": str(exc)})

    async def event_stream():
        task = asyncio.create_task(run_pipeline())
        while True:
            item = await queue.get()
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            if item.get("done"):
                break
        await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


def now():
    return datetime.utcnow()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="Default Project")
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(80), ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(40))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    detected_data_type: Mapped[str] = mapped_column(String(80), default="unknown")
    parse_status: Mapped[str] = mapped_column(String(40), default="uploaded")
    ingest_status: Mapped[str] = mapped_column(String(40), default="pending")
    vector_status: Mapped[str] = mapped_column(String(40), default="pending")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    schema_json: Mapped[str | None] = mapped_column(Text)
    preview_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    uploaded_file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id"))
    source_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(80))
    file_name: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class FeedbackItem(Base):
    __tablename__ = "feedback_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    data_source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"))
    source_type: Mapped[str] = mapped_column(String(80), default="upload")
    channel: Mapped[str | None] = mapped_column(String(80))
    user_segment: Mapped[str | None] = mapped_column(String(120))
    feedback_text: Mapped[str] = mapped_column(Text)
    feedback_summary: Mapped[str | None] = mapped_column(Text)
    sentiment_label: Mapped[str | None] = mapped_column(String(40))
    severity_label: Mapped[str | None] = mapped_column(String(40))
    product_module: Mapped[str | None] = mapped_column(String(80))
    issue_type: Mapped[str | None] = mapped_column(String(80))
    event_time: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    data_source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"))
    metric_date: Mapped[str | None] = mapped_column(String(80))
    metric_name: Mapped[str] = mapped_column(String(120))
    metric_value: Mapped[float] = mapped_column(Float, default=0)
    dimension_name: Mapped[str | None] = mapped_column(String(120))
    dimension_value: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    uploaded_file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id"))
    chunk_type: Mapped[str] = mapped_column(String(80), default="document")
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_summary: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class InsightCluster(Base):
    __tablename__ = "insight_clusters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    cluster_name: Mapped[str] = mapped_column(String(255))
    cluster_summary: Mapped[str] = mapped_column(Text)
    product_module: Mapped[str | None] = mapped_column(String(80))
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_ratio: Mapped[float] = mapped_column(Float, default=0)
    severity_score: Mapped[float] = mapped_column(Float, default=0)
    trend_score: Mapped[float] = mapped_column(Float, default=0)
    representative_quotes_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("insight_clusters.id"))
    title: Mapped[str] = mapped_column(String(255))
    problem_statement: Mapped[str] = mapped_column(Text)
    target_user: Mapped[str] = mapped_column(String(255))
    impact_score: Mapped[float] = mapped_column(Float, default=0)
    urgency_score: Mapped[float] = mapped_column(Float, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    effort_score: Mapped[float] = mapped_column(Float, default=0)
    strategic_fit_score: Mapped[float] = mapped_column(Float, default=0)
    priority_score: Mapped[float] = mapped_column(Float, default=0)
    priority_level: Mapped[str] = mapped_column(String(20), default="P2")
    evidence_ids_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PrdDocument(Base):
    __tablename__ = "prd_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"))
    title: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(40), default="v0.1")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    prd_markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    user_task: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="running")
    final_output: Mapped[str | None] = mapped_column(Text)
    report_markdown: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AgentStep(Base):
    __tablename__ = "agent_steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    agent_name: Mapped[str] = mapped_column(String(120))
    step_name: Mapped[str] = mapped_column(String(120))
    tool_name: Mapped[str | None] = mapped_column(String(120))
    input_json: Mapped[str | None] = mapped_column(Text)
    output_json: Mapped[str | None] = mapped_column(Text)
    step_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="success")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ProjectMemory(Base):
    __tablename__ = "project_memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    memory_type: Mapped[str] = mapped_column(String(80))
    content_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120))
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class UserPreferenceMemory(Base):
    __tablename__ = "user_preference_memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), default="local_user")
    preference_key: Mapped[str] = mapped_column(String(120))
    preference_value: Mapped[str] = mapped_column(Text)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DecisionMemory(Base):
    __tablename__ = "decision_memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    decision_title: Mapped[str] = mapped_column(String(255))
    decision_content: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str | None] = mapped_column(Text)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class LlmCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    agent_name: Mapped[str] = mapped_column(String(120))
    model_name: Mapped[str] = mapped_column(String(120))
    prompt_type: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    json_parse_success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    query: Mapped[str] = mapped_column(Text)
    top_k: Mapped[int] = mapped_column(Integer)
    returned_count: Mapped[int] = mapped_column(Integer)
    avg_similarity: Mapped[float] = mapped_column(Float, default=0)
    no_result: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CompressionLog(Base):
    __tablename__ = "compression_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    compression_type: Mapped[str] = mapped_column(String(80))
    original_tokens: Mapped[int] = mapped_column(Integer)
    compressed_tokens: Mapped[int] = mapped_column(Integer)
    compression_rate: Mapped[float] = mapped_column(Float)
    summary_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, default=1)
    eval_type: Mapped[str] = mapped_column(String(120))
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    metric_name: Mapped[str] = mapped_column(String(120))
    metric_value: Mapped[float] = mapped_column(Float, default=0)
    details_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SentimentAlert(Base):
    __tablename__ = "sentiment_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    target_brand: Mapped[str] = mapped_column(String(120))
    competitor_brand: Mapped[str] = mapped_column(String(120))
    dimension: Mapped[str] = mapped_column(String(120))
    gap_type: Mapped[str] = mapped_column(String(40))   # weakness/content_gap/competitor_advantage
    severity: Mapped[str] = mapped_column(String(20))   # high/medium/low
    interception_angle: Mapped[str | None] = mapped_column(Text)
    evidence_quotes: Mapped[str | None] = mapped_column(Text)  # JSON array of strings
    content_format: Mapped[str | None] = mapped_column(String(120))
    priority_rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


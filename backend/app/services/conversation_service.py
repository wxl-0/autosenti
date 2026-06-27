from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session
from app.db.models import AgentRun, Conversation, ConversationMessage


def create_conversation(db: Session, title: str | None = None, project_id: int = 1) -> Conversation:
    default_title = f"需求发现会话 {datetime.utcnow().strftime('%m-%d %H:%M')}"
    conversation = Conversation(id=str(uuid4()), project_id=project_id, title=title or default_title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def ensure_conversation(db: Session, conversation_id: str | None, project_id: int = 1) -> Conversation:
    if conversation_id:
        existing = db.get(Conversation, conversation_id)
        if existing:
            return existing
    return create_conversation(db, project_id=project_id)


def add_message(db: Session, conversation_id: str, role: str, content: str) -> ConversationMessage:
    conversation = db.get(Conversation, conversation_id)
    if conversation:
        conversation.updated_at = datetime.utcnow()
        if role == "user" and conversation.title in {"New conversation", "需求发现会话"}:
            conversation.title = content.strip()[:24] or conversation.title
    message = ConversationMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_conversations(db: Session, project_id: int = 1):
    rows = db.query(Conversation).filter_by(project_id=project_id).order_by(Conversation.updated_at.desc()).all()
    result = []
    for row in rows:
        message_count = db.query(ConversationMessage).filter_by(conversation_id=row.id).count()
        run_count = db.query(AgentRun).filter_by(conversation_id=row.id).count()
        if message_count or run_count:
            result.append(serialize_conversation(row, message_count, 0, run_count))
    return result


def get_conversation(db: Session, conversation_id: str):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        return None
    messages = db.query(ConversationMessage).filter_by(conversation_id=conversation_id).order_by(ConversationMessage.id).all()
    data = serialize_conversation(conversation, len(messages))
    data["messages"] = [serialize_message(message) for message in messages]
    return data


def serialize_conversation(row: Conversation, message_count: int = 0, file_count: int = 0, run_count: int = 0):
    return {
        "id": row.id,
        "project_id": row.project_id,
        "title": row.title,
        "message_count": message_count,
        "file_count": file_count,
        "run_count": run_count,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def serialize_message(row: ConversationMessage):
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "role": row.role,
        "content": row.content,
        "created_at": row.created_at.isoformat(),
    }

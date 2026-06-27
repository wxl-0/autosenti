from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.conversation import ConversationCreateRequest, ConversationMessageRequest
from app.services.conversation_service import add_message, create_conversation, get_conversation, list_conversations, serialize_conversation, serialize_message

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("")
def create(payload: ConversationCreateRequest, db: Session = Depends(get_db)):
    conversation = create_conversation(db, payload.title, payload.project_id)
    return serialize_conversation(conversation)


@router.get("")
def list_all(project_id: int = 1, db: Session = Depends(get_db)):
    return list_conversations(db, project_id)


@router.get("/{conversation_id}")
def detail(conversation_id: str, db: Session = Depends(get_db)):
    data = get_conversation(db, conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="conversation not found")
    return data


@router.post("/{conversation_id}/messages")
def message(conversation_id: str, payload: ConversationMessageRequest, db: Session = Depends(get_db)):
    return serialize_message(add_message(db, conversation_id, payload.role, payload.content))

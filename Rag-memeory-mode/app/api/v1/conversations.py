from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversations import ConversationRepository
from app.database.session import get_session
from app.schemas.conversation import ConversationCreateRequest, ConversationResponse
from app.security.auth import UserContext, get_current_user
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_conversation_service(
    session: AsyncSession = Depends(get_session),
    context: UserContext = Depends(get_current_user),
) -> ConversationService:
    return ConversationService(ConversationRepository(session), context)


@router.get("")
async def list_conversations(
    service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationResponse]:
    return await service.list_for_current_user()


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    payload: ConversationCreateRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    return await service.create_for_current_user(payload)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    conversation = await service.get_for_current_user(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> Response:
    if not await service.archive(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

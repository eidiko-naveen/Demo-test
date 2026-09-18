from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.chat import ChatRequest
from app.schemas.response import AgentResponse
from app.security.auth import UserContext, get_current_user
from app.utils.exceptions import LLMError

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=AgentResponse)
async def chat(
    request: Request,
    payload: ChatRequest,
    current_user: UserContext = Depends(get_current_user),
) -> AgentResponse:
    service = getattr(request.app.state, "chat_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Chat service is not configured")
    try:
        return await service.chat(
            payload,
            tenant_id=current_user.tenant_id,
            user_id=current_user.user_id,
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

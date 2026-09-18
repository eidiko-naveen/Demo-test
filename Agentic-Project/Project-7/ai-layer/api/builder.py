from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.builder_service import BuilderService
from services.validator_service import ValidatorService
from models.config import PROVIDERS

router = APIRouter()

builder_service = BuilderService()
validator_service = ValidatorService()


class BuildRequest(BaseModel):
    prompt: str
    provider: str = "gemini"
    model: str = "gemini-3.5-flash-lite"


@router.get("/health")
def health():
    return {
        "service": "AI Layer",
        "status": "healthy"
    }


@router.get("/providers")
def get_providers():
    return PROVIDERS


@router.post("/agents/build")
def build_agent(request: BuildRequest):
    try:
        if not request.prompt or len(request.prompt.strip()) == 0:
            raise HTTPException(status_code=400, detail="Prompt is required")

        if len(request.prompt.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Prompt is too short, please describe your agent in more detail"
            )

        spec = builder_service.build_agent(
            user_prompt=request.prompt,
            provider=request.provider,
            model=request.model
        )
        validation = validator_service.validate(spec)

        if not validation["valid"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Generated agent specification is invalid",
                    "errors": validation["errors"]
                }
            )

        return {
            "success": True,
            "spec": validation["spec"],
            "warnings": validation["warnings"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
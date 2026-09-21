from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.config.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class UserContext:
    user_id: str
    tenant_id: str


def resolve_user_context(
    settings: Settings, *, user_id: str | None = None, tenant_id: str | None = None
) -> UserContext:
    if settings.auth_mode.lower() == "mock":
        return UserContext(user_id or settings.mock_user_id, tenant_id or settings.mock_tenant_id)
    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Authenticated user context is required")
    return UserContext(user_id=user_id, tenant_id=tenant_id)


def get_current_user(
    settings: Settings = Depends(get_settings),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> UserContext:
    return resolve_user_context(settings, user_id=user_id, tenant_id=tenant_id)

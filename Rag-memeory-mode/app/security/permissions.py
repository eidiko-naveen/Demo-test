from app.security.auth import UserContext


def require_same_tenant(context: UserContext, tenant_id: str) -> None:
    if context.tenant_id != tenant_id:
        raise PermissionError("Tenant access denied")


def require_same_user(context: UserContext, user_id: str) -> None:
    if context.user_id != user_id:
        raise PermissionError("User access denied")

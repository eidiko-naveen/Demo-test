from dataclasses import dataclass
from typing import Protocol

from config.settings import get_settings


@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    tenant_id: str


class AuthenticationProvider(Protocol):
    def authenticate(self) -> UserIdentity:
        """Return the identity established by a trusted enterprise boundary."""


_authentication_provider: AuthenticationProvider | None = None


class DevelopmentAuthenticationProvider:
    def authenticate(self) -> UserIdentity:
        settings = get_settings()
        return UserIdentity(settings.dev_user_id, settings.dev_tenant_id)


def configure_authentication_provider(provider: AuthenticationProvider) -> None:
    """Register the trusted enterprise identity boundary during application setup."""
    global _authentication_provider
    _authentication_provider = provider


def get_current_identity() -> UserIdentity:
    """Resolve identity without accepting user-controlled browser values."""
    if get_settings().auth_mode == "enterprise":
        if _authentication_provider is None:
            raise RuntimeError("Enterprise authentication provider is not configured")
        identity = _authentication_provider.authenticate()
        if not identity.user_id or not identity.tenant_id:
            raise RuntimeError("Enterprise authentication returned an invalid identity")
        return identity
    return DevelopmentAuthenticationProvider().authenticate()
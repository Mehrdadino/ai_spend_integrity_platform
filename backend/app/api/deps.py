"""FastAPI dependencies: platform JWT, active org header, and access checks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import PlatformRole, User
from app.repositories.organizations import get_organization_by_id
from app.repositories.users import get_user_by_id
from app.services.auth.access import (
    user_can_access_organization,
    user_can_manage_organization,
    user_can_write_organization,
)
from app.services.auth.jwt_tokens import AccessTokenClaims, TokenValidationError, decode_access_token

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    """Signed-in user plus the active organization for this request."""

    organization: Organization
    user: Optional[User]


def _organization_from_header(
    x_organization_id: Optional[str],
    db: Session,
) -> Organization:
    if not x_organization_id or not x_organization_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Missing X-Organization-Id (choose an organization after sign-in)",
        )
    try:
        org_id = UUID(x_organization_id.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid X-Organization-Id") from e
    org = get_organization_by_id(db, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _user_from_claims(db: Session, claims: AccessTokenClaims) -> User:
    user = get_user_by_id(db, user_id=claims.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.role != claims.role or user.email != claims.email:
        raise HTTPException(status_code=401, detail="Token no longer valid for this user")
    if not user.password_hash:
        raise HTTPException(status_code=401, detail="User cannot sign in with password")
    return user


def require_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> User:
    """JWT only (no tenant). Used for login/session and organization list/create."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        claims = decode_access_token(credentials.credentials)
    except TokenValidationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _user_from_claims(db, claims)


def require_auth_context(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    x_organization_id: Annotated[Optional[str], Header(alias="X-Organization-Id")] = None,
) -> AuthContext:
    """JWT + active org header; enforces membership (or platform admin)."""
    if credentials is not None and credentials.credentials:
        try:
            claims = decode_access_token(credentials.credentials)
        except TokenValidationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user = _user_from_claims(db, claims)
        org = _organization_from_header(x_organization_id, db)
        if not user_can_access_organization(db, user, org):
            raise HTTPException(status_code=403, detail="You do not have access to this organization")
        return AuthContext(organization=org, user=user)

    settings = get_settings()
    if settings.auth_allow_dev_org_header:
        org = _organization_from_header(x_organization_id, db)
        return AuthContext(organization=org, user=None)

    raise HTTPException(
        status_code=401,
        detail="Sign in required (Bearer token). Dev header disabled.",
    )


def require_organization(
    ctx: AuthContext = Depends(require_auth_context),
) -> Organization:
    """Backward-compatible dependency returning only the tenant row."""
    return ctx.organization


def require_org_writer(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> AuthContext:
    """Upload, review, and other mutating product actions (not viewers)."""
    if ctx.user is None:
        raise HTTPException(
            status_code=403,
            detail="Sign in required (dev header cannot perform this action)",
        )
    if not user_can_write_organization(db, ctx.user, ctx.organization):
        raise HTTPException(status_code=403, detail="You have read-only access to this organization")
    return ctx


def require_org_manager(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> AuthContext:
    """Org admin: sites, delete docs, invites, batch materialize."""
    if ctx.user is None:
        raise HTTPException(
            status_code=403,
            detail="Sign in required (dev header cannot perform this action)",
        )
    if not user_can_manage_organization(db, ctx.user, ctx.organization):
        raise HTTPException(status_code=403, detail="You cannot manage this organization")
    return ctx


def require_org_admin_for_path_org(
    organization_id: Annotated[uuid.UUID, Path(description="Organization UUID")],
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
) -> tuple[Organization, User]:
    """Team routes: resolve org from path and require org_admin (or platform admin)."""
    org = get_organization_by_id(db, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not user_can_manage_organization(db, user, org):
        raise HTTPException(status_code=403, detail="Org admin role required")
    return org, user


def require_platform_admin(
    user: User = Depends(require_current_user),
) -> User:
    """Platform-wide admin only (reserved for future cross-tenant tools)."""
    if user.role != PlatformRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Platform admin role required")
    return user


# Backward-compatible name used by routers during rename.
require_admin = require_org_manager

"""P1 auth routes: email/password login and session introspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_current_user
from app.db.session import get_db
from app.repositories.users import get_user_by_email
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse
from app.services.auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def post_login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Exchange email/password for a JWT (platform role embedded; pick org via header afterward)."""
    user = get_user_by_email(db, email=body.email.strip())
    if user is None or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(
        user_id=user.id,
        role=user.role,
        email=user.email,
    )
    return LoginResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(require_current_user)) -> UserResponse:
    """Return the signed-in user."""
    return UserResponse.model_validate(user)

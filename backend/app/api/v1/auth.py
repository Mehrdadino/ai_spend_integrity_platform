"""P1 auth routes: register, login + email 2FA, forgot/reset password, session."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models.user import PlatformRole, User
from app.repositories.users import (
    create_user,
    get_user_by_email,
    update_user_email,
    update_user_password_hash,
)
from app.schemas.auth import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginChallengeResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    UserResponse,
    VerifyLoginOtpRequest,
)
from app.services.auth import (
    ChallengeError,
    complete_password_reset,
    create_access_token,
    hash_password,
    start_login_otp_challenge,
    start_password_reset_challenge,
    verify_login_otp_challenge,
    verify_password,
)
from app.services.auth.email_delivery import is_smtp_configured

router = APIRouter(prefix="/auth", tags=["auth"])

_FORGOT_PASSWORD_MESSAGE = (
    "If an account exists for that email, password reset instructions were sent."
)
_LOGIN_CHALLENGE_MESSAGE = "If this email is registered, a verification code was sent."


def _login_response_for_user(user: User, *, remember_device: bool = False) -> LoginResponse:
    """Mint JWT after password check (session length depends on remember_device)."""
    return LoginResponse(
        access_token=create_access_token(
            user_id=user.id,
            role=user.role,
            email=user.email,
            remember_device=remember_device,
        ),
        user=UserResponse.model_validate(user),
    )


def _require_current_password(user: User, current_password: str) -> None:
    """Verify password for account settings mutations."""
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def post_register(body: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """Create a member account (email + password). Sign-in requires email OTP afterward."""
    settings = get_settings()
    if not settings.auth_allow_registration:
        raise HTTPException(status_code=403, detail="Registration is disabled")

    email = str(body.email).strip().lower()
    if get_user_by_email(db, email=email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = create_user(
        db,
        email=email,
        password_hash=hash_password(body.password),
        role=PlatformRole.MEMBER.value,
        organization_id=None,
    )
    db.commit()
    return RegisterResponse(
        message="Account created. Sign in with your email and password.",
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=LoginChallengeResponse)
def post_login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginChallengeResponse:
    """Validate email/password; email OTP when SMTP is configured, else sign in directly (local dev)."""
    user = get_user_by_email(db, email=body.email.strip())
    if user is None or not user.password_hash:
        # Same response shape as success to avoid account enumeration.
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not is_smtp_configured():
        login = _login_response_for_user(user, remember_device=body.remember_device)
        return LoginChallengeResponse(
            message="Signed in.",
            access_token=login.access_token,
            user=login.user,
        )

    try:
        result = start_login_otp_challenge(db, user=user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return LoginChallengeResponse(
        challenge_id=result.challenge_id,
        message=_LOGIN_CHALLENGE_MESSAGE,
    )


@router.post("/login/verify-2fa", response_model=LoginResponse)
def post_verify_login_otp(
    body: VerifyLoginOtpRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Exchange email OTP for a JWT."""
    try:
        user = verify_login_otp_challenge(
            db,
            challenge_id=body.challenge_id,
            otp_code=body.code,
        )
        db.commit()
    except ChallengeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return _login_response_for_user(user, remember_device=body.remember_device)


@router.post("/forgot-password", response_model=MessageResponse)
def post_forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Email a reset link only when the account exists (same response either way)."""
    email = str(body.email).strip().lower()
    user = get_user_by_email(db, email=email)
    if user is not None and user.password_hash:
        try:
            start_password_reset_challenge(db, user=user)
            db.commit()
        except Exception:
            db.rollback()
            raise

    return MessageResponse(message=_FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def post_reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Set a new password using the token from the reset email."""
    try:
        complete_password_reset(
            db,
            reset_token=body.reset_token,
            new_password=body.new_password,
        )
        db.commit()
    except ChallengeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return MessageResponse(message="Password updated. You can sign in with your new password.")


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(require_current_user)) -> UserResponse:
    """Return the signed-in user."""
    return UserResponse.model_validate(user)


@router.post("/change-password", response_model=MessageResponse)
def post_change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
) -> MessageResponse:
    """Replace password for the signed-in user."""
    _require_current_password(user, body.current_password)
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current password")

    update_user_password_hash(db, user, password_hash=hash_password(body.new_password))
    db.commit()
    return MessageResponse(message="Password updated.")


@router.post("/change-email", response_model=LoginResponse)
def post_change_email(
    body: ChangeEmailRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
) -> LoginResponse:
    """Replace login email; returns a fresh JWT (old tokens become invalid)."""
    _require_current_password(user, body.current_password)
    new_email = str(body.new_email).strip().lower()
    if new_email == user.email:
        raise HTTPException(status_code=400, detail="New email is the same as your current email")

    existing = get_user_by_email(db, email=new_email)
    if existing is not None and existing.id != user.id:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    update_user_email(db, user, email=new_email)
    db.commit()
    db.refresh(user)
    return _login_response_for_user(user, remember_device=True)

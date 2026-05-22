"""P1 auth routes: register, login + email 2FA, forgot/reset password, session."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_current_user
from app.api.rate_limit_deps import rate_limit_auth_ip
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
from app.schemas.organization_team import (
    AcceptOrganizationInviteRequest,
    AcceptOrganizationInviteResponse,
    ActivateOrganizationInviteRequest,
    ActivateOrganizationInviteResponse,
    OrganizationInvitePreviewResponse,
)
from app.services.organization_invites import InviteError, accept_invite, activate_invite, preview_invite
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
from app.services.auth_lockout import (
    assert_login_not_locked,
    clear_login_failures,
    record_login_failure,
)
from app.services.rate_limit import enforce_rate_limit_email

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


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth_ip("register"))],
)
def post_register(body: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """Create a member account (email + password). Sign-in requires email OTP afterward."""
    settings = get_settings()
    if not settings.auth_allow_registration:
        raise HTTPException(status_code=403, detail="Registration is disabled")

    email = str(body.email).strip().lower()
    enforce_rate_limit_email("register", email)
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


@router.post(
    "/login",
    response_model=LoginChallengeResponse,
    dependencies=[Depends(rate_limit_auth_ip("login"))],
)
def post_login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginChallengeResponse:
    """Validate email/password; email OTP when SMTP is configured, else sign in directly (local dev)."""
    email = body.email.strip().lower()
    enforce_rate_limit_email("login", email)
    assert_login_not_locked(email)

    user = get_user_by_email(db, email=email)
    if user is None or not user.password_hash:
        record_login_failure(email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        record_login_failure(email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    clear_login_failures(email)

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


@router.post(
    "/login/verify-2fa",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit_auth_ip("verify_2fa"))],
)
def post_verify_login_otp(
    body: VerifyLoginOtpRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Exchange email OTP for a JWT."""
    enforce_rate_limit_email("verify_2fa", str(body.challenge_id))
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


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth_ip("forgot_password"))],
)
def post_forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Email a reset link only when the account exists (same response either way)."""
    email = str(body.email).strip().lower()
    enforce_rate_limit_email("forgot_password", email)
    user = get_user_by_email(db, email=email)
    if user is not None and user.password_hash:
        try:
            start_password_reset_challenge(db, user=user)
            db.commit()
        except Exception:
            db.rollback()
            raise

    return MessageResponse(message=_FORGOT_PASSWORD_MESSAGE)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth_ip("reset_password"))],
)
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


@router.post(
    "/change-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth_ip("change_password"))],
)
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


@router.get(
    "/invite-preview",
    response_model=OrganizationInvitePreviewResponse,
    dependencies=[Depends(rate_limit_auth_ip("invite_preview"))],
)
def get_invite_preview(
    invite_token: str = Query(min_length=16, max_length=256),
    db: Session = Depends(get_db),
) -> OrganizationInvitePreviewResponse:
    """Public metadata for an invite link (new user vs existing account)."""
    try:
        preview = preview_invite(db, token=invite_token)
    except InviteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrganizationInvitePreviewResponse(
        email=preview.email,
        organization_id=preview.organization_id,
        organization_name=preview.organization_name,
        role=preview.role,
        account_exists=preview.account_exists,
    )


@router.post(
    "/activate-invite",
    response_model=ActivateOrganizationInviteResponse,
    dependencies=[Depends(rate_limit_auth_ip("activate_invite"))],
)
def post_activate_invite(
    body: ActivateOrganizationInviteRequest,
    db: Session = Depends(get_db),
) -> ActivateOrganizationInviteResponse:
    """Create account + org membership from invite token (B2B activation flow)."""
    try:
        user, invite = activate_invite(db, token=body.invite_token, password=body.password)
        db.commit()
        db.refresh(user)
    except InviteError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    org = invite.organization
    org_name = org.name if org is not None else "the organization"
    return ActivateOrganizationInviteResponse(
        access_token=create_access_token(
            user_id=user.id,
            role=user.role,
            email=user.email,
            remember_device=body.remember_device,
        ),
        user=UserResponse.model_validate(user),
        organization_id=invite.organization_id,
        organization_name=org_name,
        role=invite.role,
        message=f"Welcome — you joined {org_name}.",
    )


@router.post(
    "/accept-invite",
    response_model=AcceptOrganizationInviteResponse,
    dependencies=[Depends(rate_limit_auth_ip("accept_invite"))],
)
def post_accept_invite(
    body: AcceptOrganizationInviteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
) -> AcceptOrganizationInviteResponse:
    """Join an organization using the token from an invite email."""
    try:
        invite = accept_invite(db, token=body.invite_token, user=user)
        db.commit()
    except InviteError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    org = invite.organization
    return AcceptOrganizationInviteResponse(
        organization_id=org.id,
        organization_name=org.name,
        role=invite.role,
        message=f"You joined {org.name}.",
    )

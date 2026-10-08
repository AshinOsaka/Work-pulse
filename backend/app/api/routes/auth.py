from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AuthServiceDep, MfaServiceDep, RequestMetaDep
from app.auth.dependencies import CurrentPrincipal
from app.auth.permissions import permissions_for_role
from app.core.config import Settings
from app.core.dependencies import SettingsDep
from app.core.exceptions import UnauthorizedError, app_error_response
from app.core.security import MFA_CHALLENGE_MINUTES
from app.schemas.auth import (
    AcceptInvitationRequest,
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    InvitationPreview,
    LoginRequest,
    MfaChallengeResponse,
    MfaCodeRequest,
    MfaManageRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    PasswordConfirmRequest,
    RecoveryCodesResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionOut,
    SessionResponse,
    SessionsRevokedResponse,
    VerifyEmailRequest,
    describe_user_agent,
)
from app.schemas.common import MessageResponse
from app.schemas.company import CompanyOut
from app.schemas.user import UserOut
from app.services.auth_service import AuthResult, MfaChallenge
from app.utils.time import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        user=UserOut.from_model(result.user),
        company=CompanyOut.from_model(result.company),
        permissions=sorted(permissions_for_role(result.user.role)),
        access_token=result.tokens.access_token,
        expires_in=result.tokens.expires_in,
    )


def _set_refresh_cookie(response: Response, result: AuthResult, settings: Settings) -> None:
    max_age = int((result.tokens.refresh_expires_at - utcnow()).total_seconds())
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=result.tokens.refresh_token,
        max_age=max_age,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    meta: RequestMetaDep,
) -> AuthResponse:
    """Create a new company workspace with its first Company Admin."""
    result = await service.register_company(payload, meta)
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


@router.post("/login", response_model=AuthResponse | MfaChallengeResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    meta: RequestMetaDep,
) -> AuthResponse | MfaChallengeResponse:
    """Sign in. Accounts with two-step verification get a short-lived challenge to complete at `/auth/mfa/verify`."""
    result = await service.authenticate(payload.email, payload.password, meta)
    if isinstance(result, MfaChallenge):
        return MfaChallengeResponse(challenge=result.challenge, expires_in=MFA_CHALLENGE_MINUTES * 60)
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


@router.post("/mfa/verify", response_model=AuthResponse, summary="Second sign-in step")
async def verify_mfa(
    payload: MfaVerifyRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    meta: RequestMetaDep,
) -> AuthResponse:
    result = await service.complete_mfa(payload.challenge, payload.code, meta)
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    meta: RequestMetaDep,
) -> AuthResponse | JSONResponse:
    """Rotate the refresh-token cookie and return a fresh access token + session."""
    raw = request.cookies.get(settings.refresh_cookie_name)
    try:
        if not raw:
            raise UnauthorizedError("No active session.", code="missing_refresh_token")
        result = await service.refresh_session(raw, meta)
    except UnauthorizedError as exc:
        error = app_error_response(exc)
        _clear_refresh_cookie(error, settings)
        return error
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, service: AuthServiceDep, settings: SettingsDep, meta: RequestMetaDep
) -> Response:
    """End this browser's session (its access tokens stop working immediately)."""
    await service.logout(request.cookies.get(settings.refresh_cookie_name), meta)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, settings)
    return response


@router.get("/me", response_model=SessionResponse)
async def me(principal: CurrentPrincipal, service: AuthServiceDep) -> SessionResponse:
    user, company = await service.get_session(principal.user)
    return SessionResponse(
        user=UserOut.from_model(user),
        company=CompanyOut.from_model(company),
        permissions=sorted(principal.permissions),
    )


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest, service: AuthServiceDep, meta: RequestMetaDep
) -> MessageResponse:
    await service.request_password_reset(payload.email, meta)
    return MessageResponse(
        message="If an account exists for that email, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest, service: AuthServiceDep, meta: RequestMetaDep
) -> MessageResponse:
    await service.reset_password(payload.token, payload.password, meta)
    return MessageResponse(message="Your password has been reset. You can now sign in.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest, service: AuthServiceDep, meta: RequestMetaDep
) -> MessageResponse:
    await service.verify_email(payload.token, meta)
    return MessageResponse(message="Your email address has been verified.")


@router.post("/resend-verification", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(principal: CurrentPrincipal, service: AuthServiceDep) -> MessageResponse:
    await service.resend_verification(principal.user)
    return MessageResponse(message="A new verification link has been sent.")


@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    principal: CurrentPrincipal,
    service: AuthServiceDep,
    settings: SettingsDep,
    meta: RequestMetaDep,
) -> AuthResponse:
    """Change password, sign out all other sessions and issue a new session."""
    result = await service.change_password(
        principal.user, payload.current_password, payload.new_password, meta
    )
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


@router.get("/invitations/{token}", response_model=InvitationPreview, summary="Preview a pending invitation")
async def preview_invitation(token: str, service: AuthServiceDep) -> InvitationPreview:
    return await service.preview_invitation(token)


@router.post("/invitations/accept", response_model=AuthResponse)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    meta: RequestMetaDep,
) -> AuthResponse:
    """Set a password for an invited account and sign in."""
    result = await service.accept_invitation(payload, meta)
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


# --------------------------------------------------------------------------- sessions
@router.get("/sessions", response_model=list[SessionOut], summary="Where you are signed in")
async def sessions(principal: CurrentPrincipal, service: AuthServiceDep) -> list[SessionOut]:
    return [
        SessionOut(
            id=str(s.id),
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            device=describe_user_agent(s.user_agent),
            ip_address=s.ip_address,
            mfa=s.mfa,
            current=s.id == principal.session_id,
        )
        for s in await service.list_sessions(principal.user)
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str, principal: CurrentPrincipal, service: AuthServiceDep, meta: RequestMetaDep
) -> Response:
    """Sign out one session. Its access tokens stop working at once and its live connections are closed."""
    await service.revoke_session(principal.user, session_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-others", response_model=SessionsRevokedResponse)
async def revoke_other_sessions(
    principal: CurrentPrincipal, service: AuthServiceDep, meta: RequestMetaDep
) -> SessionsRevokedResponse:
    """Sign out everywhere except this browser."""
    return SessionsRevokedResponse(
        revoked=await service.revoke_other_sessions(principal.user, principal.session_id, meta)
    )


# --------------------------------------------------------------------------- two-step verification
@router.post("/mfa/setup", response_model=MfaSetupResponse, summary="Start setting up an authenticator app")
async def mfa_setup(
    payload: PasswordConfirmRequest, principal: CurrentPrincipal, mfa: MfaServiceDep
) -> MfaSetupResponse:
    setup = await mfa.begin_setup(principal.user, payload.password)
    return MfaSetupResponse(secret=setup.secret, uri=setup.uri, qr_svg=setup.qr_svg)


@router.post(
    "/mfa/enable", response_model=RecoveryCodesResponse, summary="Confirm the first code and turn it on"
)
async def mfa_enable(
    payload: MfaCodeRequest, principal: CurrentPrincipal, mfa: MfaServiceDep, meta: RequestMetaDep
) -> RecoveryCodesResponse:
    return RecoveryCodesResponse(codes=await mfa.confirm_setup(principal.user, payload.code, meta))


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_disable(
    payload: MfaManageRequest, principal: CurrentPrincipal, mfa: MfaServiceDep, meta: RequestMetaDep
) -> Response:
    await mfa.disable(principal.user, payload.password, payload.code, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/mfa/recovery-codes", response_model=RecoveryCodesResponse, summary="Replace your recovery codes"
)
async def mfa_recovery_codes(
    payload: MfaManageRequest, principal: CurrentPrincipal, mfa: MfaServiceDep, meta: RequestMetaDep
) -> RecoveryCodesResponse:
    return RecoveryCodesResponse(
        codes=await mfa.regenerate_recovery_codes(principal.user, payload.password, payload.code, meta)
    )

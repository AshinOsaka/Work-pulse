"""Authentication use-cases: registration, sign-in, sessions, password & e-mail flows."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.permissions import Role
from app.core.config import Settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
    UnauthorizedError,
)
from app.core.security import (
    burn_password_check,
    create_mfa_challenge,
    decode_mfa_challenge,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.models.auth_tokens import EmailVerificationToken, InvitationToken, PasswordResetToken
from app.models.company import Company, CompanyStatus
from app.models.organization import Employee, EmployeeStatus
from app.models.security import AuthSession
from app.models.user import User, UserStatus
from app.repositories.auth_tokens import (
    EmailVerificationTokenRepository,
    InvitationTokenRepository,
    PasswordResetTokenRepository,
)
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.schemas.auth import AcceptInvitationRequest, InvitationPreview, RegisterRequest
from app.services import throttle as limits
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.email_service import EmailDeliveryError, EmailService
from app.services.mfa_service import MfaService
from app.services.throttle import Throttle
from app.services.token_service import IssuedTokens, TokenService
from app.utils.text import normalise_email, slugify
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

_INVALID_CREDENTIALS = "Invalid email or password."


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    company: Company
    tokens: IssuedTokens


@dataclass(frozen=True, slots=True)
class MfaChallenge:
    """The password was right; a second factor is needed before a session is created."""

    challenge: str


class AuthService:
    def __init__(
        self,
        *,
        settings: Settings,
        users: UserRepository,
        companies: CompanyRepository,
        tokens: TokenService,
        reset_tokens: PasswordResetTokenRepository,
        verification_tokens: EmailVerificationTokenRepository,
        invitations: InvitationTokenRepository,
        employees: EmployeeRepository,
        email: EmailService,
        audit: AuditService,
        throttle: Throttle,
        mfa: MfaService,
    ) -> None:
        self._settings = settings
        self._users = users
        self._companies = companies
        self._tokens = tokens
        self._reset_tokens = reset_tokens
        self._verification_tokens = verification_tokens
        self._invitations = invitations
        self._employees = employees
        self._email = email
        self._audit = audit
        self._throttle = throttle
        self._mfa = mfa

    # ------------------------------------------------------------------ register
    async def register_company(self, data: RegisterRequest, meta: RequestMeta) -> AuthResult:
        await self._throttle.hit(limits.REGISTER_PER_IP, meta.ip_address)
        email = normalise_email(data.email)
        if await self._users.email_exists(email):
            raise ConflictError("An account with this email already exists.", code="email_taken")

        company = Company(
            name=data.company_name,
            slug=await self._unique_slug(data.company_name),
            timezone=data.timezone,
            industry=data.industry,
            size=data.company_size,
            trial_ends_at=utcnow() + timedelta(days=self._settings.trial_period_days),
        )
        try:
            await self._companies.create(company)
        except DuplicateKeyError as exc:
            raise ConflictError("Workspace name is already taken.", code="slug_taken") from exc

        user = User(
            company_id=company.id,
            email=email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=Role.COMPANY_ADMIN,
            status=UserStatus.ACTIVE,
            password_changed_at=utcnow(),
        )
        try:
            await self._users.create(company.id, user)
        except DuplicateKeyError as exc:
            # Standalone MongoDB has no multi-document transactions: compensate.
            await self._companies.delete_by_id(company.id)
            raise ConflictError("An account with this email already exists.", code="email_taken") from exc

        # The founding admin is also an employee of their own workspace.
        employee = Employee(company_id=company.id, full_name=user.full_name, email=email, user_id=user.id)
        await self._employees.create(company.id, employee)
        user = await self._users.update_by_id(company.id, user.id, {"employee_id": employee.id}) or user

        await self._send_verification(user)
        tokens = await self._tokens.issue(user, meta)
        await self._audit.record(
            "company.registered",
            company_id=company.id,
            actor_user_id=user.id,
            target_type="company",
            target_id=str(company.id),
            meta=meta,
        )
        return AuthResult(user, company, tokens)

    async def _unique_slug(self, name: str) -> str:
        base = slugify(name)
        candidate = base
        for _ in range(5):
            if not await self._companies.slug_exists(candidate):
                return candidate
            candidate = f"{base}-{secrets.token_hex(3)}"
        raise ConflictError("Could not allocate a workspace identifier.", code="slug_taken")

    # ------------------------------------------------------------------ sessions
    async def authenticate(self, email: str, password: str, meta: RequestMeta) -> AuthResult | MfaChallenge:
        address = normalise_email(email)
        await self._throttle.hit(limits.LOGIN_PER_IP, meta.ip_address)
        await self._throttle.check(limits.LOGIN_FAILURES_PER_ACCOUNT, address)
        user = await self._users.find_by_email_for_auth(address)
        if user is None:
            burn_password_check(password)
            await self._throttle.fail(limits.LOGIN_FAILURES_PER_ACCOUNT, address)
            raise UnauthorizedError(_INVALID_CREDENTIALS, code="invalid_credentials")

        if not verify_password(user.password_hash, password):
            await self._throttle.fail(limits.LOGIN_FAILURES_PER_ACCOUNT, address)
            await self._audit.record(
                "auth.login_failed", company_id=user.company_id, actor_user_id=user.id, meta=meta
            )
            raise UnauthorizedError(_INVALID_CREDENTIALS, code="invalid_credentials")

        self._ensure_can_sign_in(user)
        company = await self._load_active_company(user.company_id)
        await self._throttle.clear(limits.LOGIN_FAILURES_PER_ACCOUNT, address)
        if password_needs_rehash(user.password_hash):
            user = (
                await self._users.update_by_id(
                    user.company_id, user.id, {"password_hash": hash_password(password)}
                )
                or user
            )
        if user.mfa_enabled:
            return MfaChallenge(
                create_mfa_challenge(
                    user_id=str(user.id), company_id=str(user.company_id), settings=self._settings
                )
            )
        return await self._sign_in(user, company, meta, second_factor=None)

    async def complete_mfa(self, challenge: str, code: str, meta: RequestMeta) -> AuthResult:
        """Second sign-in step: the challenge from the password step plus an authenticator or recovery code."""
        user_id, company_id = decode_mfa_challenge(challenge, self._settings)
        await self._throttle.check(limits.MFA_FAILURES_PER_ACCOUNT, user_id)
        if not ObjectId.is_valid(user_id) or not ObjectId.is_valid(company_id):
            raise UnauthorizedError("Please sign in again.", code="invalid_mfa_challenge")
        user = await self._users.get_by_id(ObjectId(company_id), ObjectId(user_id))
        if user is None or not user.mfa_enabled:
            raise UnauthorizedError("Please sign in again.", code="invalid_mfa_challenge")
        self._ensure_can_sign_in(user)
        company = await self._load_active_company(user.company_id)
        method = await self._mfa.verify(user, code)
        if method is None:
            await self._throttle.fail(limits.MFA_FAILURES_PER_ACCOUNT, user_id)
            await self._audit.record(
                "auth.mfa_failed", company_id=user.company_id, actor_user_id=user.id, meta=meta
            )
            raise UnauthorizedError("That code didn't match.", code="invalid_mfa_code")
        await self._throttle.clear(limits.MFA_FAILURES_PER_ACCOUNT, user_id)
        return await self._sign_in(user, company, meta, second_factor=method)

    async def _sign_in(
        self, user: User, company: Company, meta: RequestMeta, *, second_factor: str | None
    ) -> AuthResult:
        user = await self._users.update_by_id(user.company_id, user.id, {"last_login_at": utcnow()}) or user
        tokens = await self._tokens.issue(user, meta, mfa=second_factor is not None)
        await self._audit.record(
            "auth.login",
            company_id=user.company_id,
            actor_user_id=user.id,
            meta=meta,
            metadata={"session_id": str(tokens.session_id), "second_factor": second_factor},
        )
        return AuthResult(user, company, tokens)

    async def refresh_session(self, raw_refresh: str, meta: RequestMeta) -> AuthResult:
        record, session_id = await self._tokens.consume(raw_refresh)
        user = await self._users.get_by_id(record.company_id, record.user_id)
        if user is None:
            raise UnauthorizedError("Your session is no longer valid.", code="invalid_refresh_token")
        self._ensure_can_sign_in(user)
        company = await self._load_active_company(user.company_id)
        tokens = await self._tokens.issue(user, meta, session_id=session_id)
        return AuthResult(user, company, tokens)

    async def logout(self, raw_refresh: str | None, meta: RequestMeta) -> None:
        if not raw_refresh:
            return
        record = await self._tokens.revoke(raw_refresh, "logout")
        if record is not None:
            await self._audit.record(
                "auth.logout",
                company_id=record.company_id,
                actor_user_id=record.user_id,
                meta=meta,
                metadata={"session_id": record.family_id},
            )

    # ------------------------------------------------------------------ session management
    async def list_sessions(self, user: User) -> list[AuthSession]:
        return await self._tokens.sessions.for_user(user.company_id, user.id)

    async def revoke_session(self, user: User, session_id: str, meta: RequestMeta) -> None:
        if not ObjectId.is_valid(session_id) or not await self._tokens.revoke_session(
            user, ObjectId(session_id), "signed_out_remotely"
        ):
            raise NotFoundError("Session not found.", code="session_not_found")
        await self._audit.record(
            "auth.session_revoked",
            company_id=user.company_id,
            actor_user_id=user.id,
            meta=meta,
            metadata={"session_id": session_id},
        )

    async def revoke_other_sessions(self, user: User, keep: ObjectId | None, meta: RequestMeta) -> int:
        ended = await self._tokens.revoke_all(user, "signed_out_everywhere", keep=keep)
        await self._audit.record(
            "auth.sessions_revoked",
            company_id=user.company_id,
            actor_user_id=user.id,
            meta=meta,
            metadata={"sessions": len(ended), "kept_current": keep is not None},
        )
        return len(ended)

    async def revoke_user_sessions(self, actor: User, target: User, meta: RequestMeta) -> int:
        """An administrator signs someone out everywhere (lost laptop, departure, suspected compromise)."""
        ended = await self._tokens.revoke_all(target, "revoked_by_admin")
        await self._audit.record(
            "user.sessions_revoked",
            company_id=target.company_id,
            actor_user_id=actor.id,
            target_type="user",
            target_id=str(target.id),
            subject_employee_id=target.employee_id,
            meta=meta,
            metadata={"sessions": len(ended)},
        )
        return len(ended)

    async def get_session(self, user: User) -> tuple[User, Company]:
        company = await self._companies.get_by_id(user.company_id)
        if company is None:
            raise UnauthorizedError("Workspace no longer exists.", code="company_not_found")
        return user, company

    @staticmethod
    def _ensure_can_sign_in(user: User) -> None:
        if user.status == UserStatus.SUSPENDED:
            raise ForbiddenError("This account has been suspended.", code="account_suspended")
        if user.status == UserStatus.DEACTIVATED:
            raise ForbiddenError("This account has been deactivated.", code="account_deactivated")
        if user.status == UserStatus.INVITED:
            raise ForbiddenError("This account has not been activated yet.", code="account_not_activated")

    async def _load_active_company(self, company_id: ObjectId) -> Company:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise UnauthorizedError("Workspace no longer exists.", code="company_not_found")
        if company.status == CompanyStatus.SUSPENDED:
            raise ForbiddenError("This workspace has been suspended.", code="company_suspended")
        return company

    # ------------------------------------------------------------------ passwords
    async def request_password_reset(self, email: str, meta: RequestMeta) -> None:
        """Always succeeds from the caller's perspective to prevent account enumeration."""
        await self._throttle.hit(limits.PASSWORD_RESET_PER_IP, meta.ip_address)
        address = normalise_email(email)
        try:
            await self._throttle.hit(limits.PASSWORD_RESET_PER_ACCOUNT, address)
        except TooManyRequestsError:
            return  # silently: an error would reveal that this address was tried before
        user = await self._users.find_by_email_for_auth(address)
        if user is None or user.status != UserStatus.ACTIVE:
            return

        await self._reset_tokens.invalidate_for_user(user.company_id, user.id)
        raw = generate_opaque_token()
        await self._reset_tokens.create(
            user.company_id,
            PasswordResetToken(
                company_id=user.company_id,
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=utcnow() + timedelta(minutes=self._settings.password_reset_token_expire_minutes),
            ),
        )
        try:
            await self._email.send_password_reset(to=user.email, name=user.full_name, token=raw)
        except EmailDeliveryError:
            # Same answer as for unknown addresses, or a mail outage would reveal which accounts exist. The failure
            # is logged and counted (workpulse_emails_total{outcome="failed"}) so operators see it.
            logger.warning("Password reset e-mail for user %s could not be sent", user.id)
            return
        await self._audit.record(
            "auth.password_reset_requested", company_id=user.company_id, actor_user_id=user.id, meta=meta
        )

    async def reset_password(self, raw_token: str, new_password: str, meta: RequestMeta) -> None:
        await self._throttle.hit(limits.TOKEN_REDEEM_PER_IP, meta.ip_address)
        record = await self._reset_tokens.find_valid_by_hash(hash_token(raw_token))
        if record is None or not await self._reset_tokens.mark_used(record.id):
            raise BadRequestError("This reset link is invalid or has expired.", code="invalid_reset_token")

        user = await self._users.get_by_id(record.company_id, record.user_id)
        if user is None:
            raise BadRequestError("This reset link is invalid or has expired.", code="invalid_reset_token")

        await self._set_password(user, new_password)
        await self._tokens.revoke_all(user, "password_reset")
        await self._audit.record(
            "auth.password_reset", company_id=user.company_id, actor_user_id=user.id, meta=meta
        )

    async def change_password(
        self, user: User, current_password: str, new_password: str, meta: RequestMeta
    ) -> AuthResult:
        if not verify_password(user.password_hash, current_password):
            raise BadRequestError("Current password is incorrect.", code="invalid_current_password")
        if current_password == new_password:
            raise BadRequestError("New password must be different.", code="password_unchanged")

        user = await self._set_password(user, new_password)
        await self._tokens.revoke_all(user, "password_changed")
        company = await self._load_active_company(user.company_id)
        # Every other session ends; this browser gets a fresh one (it already passed any second factor).
        tokens = await self._tokens.issue(user, meta, mfa=user.mfa_enabled)
        await self._audit.record(
            "auth.password_changed", company_id=user.company_id, actor_user_id=user.id, meta=meta
        )
        return AuthResult(user, company, tokens)

    async def _set_password(self, user: User, new_password: str) -> User:
        updated = await self._users.update_by_id(
            user.company_id,
            user.id,
            {"password_hash": hash_password(new_password), "password_changed_at": utcnow()},
        )
        return updated or user

    # ------------------------------------------------------------------ e-mail verification
    async def _send_verification(self, user: User) -> None:
        await self._verification_tokens.invalidate_for_user(user.company_id, user.id)
        raw = generate_opaque_token()
        await self._verification_tokens.create(
            user.company_id,
            EmailVerificationToken(
                company_id=user.company_id,
                user_id=user.id,
                email=user.email,
                token_hash=hash_token(raw),
                expires_at=utcnow() + timedelta(hours=self._settings.email_verification_token_expire_hours),
            ),
        )
        await self._email.send_email_verification(to=user.email, name=user.full_name, token=raw)

    async def resend_verification(self, user: User) -> None:
        if user.email_verified:
            raise BadRequestError("Your email address is already verified.", code="email_already_verified")
        await self._send_verification(user)

    async def verify_email(self, raw_token: str, meta: RequestMeta) -> None:
        await self._throttle.hit(limits.TOKEN_REDEEM_PER_IP, meta.ip_address)
        record = await self._verification_tokens.find_valid_by_hash(hash_token(raw_token))
        if record is None:
            raise BadRequestError(
                "This verification link is invalid or has expired.", code="invalid_verification_token"
            )

        user = await self._users.get_by_id(record.company_id, record.user_id)
        if user is None or user.email != record.email:
            raise BadRequestError(
                "This verification link is invalid or has expired.", code="invalid_verification_token"
            )

        await self._verification_tokens.mark_used(record.id)
        await self._users.update_by_id(
            user.company_id, user.id, {"email_verified": True, "email_verified_at": utcnow()}
        )
        await self._audit.record(
            "auth.email_verified", company_id=user.company_id, actor_user_id=user.id, meta=meta
        )

    # ------------------------------------------------------------------ invitations
    async def preview_invitation(self, raw_token: str) -> InvitationPreview:
        record, user, company = await self._load_invitation(raw_token)
        return InvitationPreview(
            email=user.email,
            full_name=user.full_name,
            company_name=company.name,
            expires_at=record.expires_at,
        )

    async def accept_invitation(self, data: AcceptInvitationRequest, meta: RequestMeta) -> AuthResult:
        await self._throttle.hit(limits.TOKEN_REDEEM_PER_IP, meta.ip_address)
        record, user, company = await self._load_invitation(data.token)
        if not await self._invitations.mark_used(record.id):
            raise BadRequestError("This invitation is invalid or has expired.", code="invalid_invitation")

        now = utcnow()
        changes: dict[str, object] = {
            "password_hash": hash_password(data.password),
            "password_changed_at": now,
            "status": UserStatus.ACTIVE,
            # Accepting a link sent to this address proves ownership of it.
            "email_verified": True,
            "email_verified_at": now,
            "last_login_at": now,
        }
        if data.full_name:
            changes["full_name"] = data.full_name
        activated = await self._users.update_by_id(company.id, user.id, changes)
        if activated is None:
            raise BadRequestError("This invitation is invalid or has expired.", code="invalid_invitation")
        if data.full_name and activated.employee_id:
            await self._employees.update_by_id(
                company.id, activated.employee_id, {"full_name": data.full_name}
            )

        tokens = await self._tokens.issue(activated, meta)
        await self._audit.record(
            "invitation.accepted",
            company_id=company.id,
            actor_user_id=activated.id,
            subject_employee_id=activated.employee_id,
            meta=meta,
        )
        return AuthResult(activated, company, tokens)

    async def _load_invitation(self, raw_token: str) -> tuple[InvitationToken, User, Company]:
        invalid = BadRequestError("This invitation is invalid or has expired.", code="invalid_invitation")
        record = await self._invitations.find_valid_by_hash(hash_token(raw_token))
        if record is None:
            raise invalid
        user = await self._users.get_by_id(record.company_id, record.user_id)
        if user is None or user.status != UserStatus.INVITED or user.email != record.email:
            raise invalid
        if user.employee_id:
            employee = await self._employees.get_by_id(record.company_id, user.employee_id)
            if employee is None or employee.status == EmployeeStatus.TERMINATED:
                raise invalid
        company = await self._load_active_company(record.company_id)
        return record, user, company
